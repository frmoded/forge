"""Composition helpers for snippets.

These functions are pre-injected into the snippet namespace by the executor
(see _FORGE_MUSIC_LIB_NAMES in forge.core.executor). They wrap common
music21 patterns — bar building, voice combination, sequencing, scales,
and repetition — so snippet authors can express compositions in a few
lines without re-deriving the boilerplate each time.

All composition operations return Score (uniform return type hides the
Part/Score asymmetry of music21). `bar` returns Measure because it's a
building block, not a finished artifact.
"""
from __future__ import annotations

import copy
from typing import Union

# v0.2.171 — split the multi-name music21 import so a single missing
# submodule (e.g. partial pyodide wheel) doesn't kill the whole forge.music.lib
# import. Each line is independent; if `tempo` (added in v0.2.166) isn't
# available, the others still load and the chips that don't need tempo still
# work.
from music21 import clef, instrument, key, meter, note, pitch, stream
try:
  from music21 import tempo
except ImportError:
  tempo = None

# v0.7.0 — additional music21 submodules used by the promoted
# forge-music library notes (form/chord, harmony for chord symbols,
# duration for explicit Duration objects, roman for Roman-numeral
# resolution). Each import is independent so a partial wheel doesn't
# kill the rest of lib.
try:
  from music21 import chord
except ImportError:
  chord = None
try:
  from music21 import harmony
except ImportError:
  harmony = None
try:
  from music21 import duration
except ImportError:
  duration = None
try:
  from music21 import roman
except ImportError:
  roman = None

# Standard-library random — needed by guitar_solo_chorus / vocal_phrase_*
# library notes (v0.7.0 promotion). Imported under a private alias so
# the public lib namespace doesn't shadow callers' own `random`.
import random as _random

StreamLike = Union[stream.Score, stream.Part, stream.Measure, stream.Stream]


def bar(
  *items: note.GeneralNote,
  time_signature: meter.TimeSignature | None = None,
  number: int | None = None,
) -> stream.Measure:
  """Build a Measure from notes/rests, padding with a trailing Rest if the
  items are shorter than the bar length. Defaults to 4/4."""
  ts = time_signature if time_signature is not None else meter.TimeSignature('4/4')
  bar_ql = ts.barDuration.quarterLength

  total_ql = sum(item.duration.quarterLength for item in items)
  if total_ql > bar_ql:
    raise ValueError(
      f"bar(): items total {total_ql} quarterLength but bar is {bar_ql}. "
      f"Trim items or remove some to fit."
    )

  m = stream.Measure()
  if number is not None:
    m.number = number
  m.append(ts)
  for item in items:
    m.append(copy.deepcopy(item))

  remaining = bar_ql - total_ql
  if remaining > 0:
    m.append(note.Rest(quarterLength=remaining))
  return m


def voices(
  *streams: StreamLike,
  instruments: list[str] | None = None,
) -> stream.Score:
  """Combine streams as simultaneous Parts in a single Score. Each input
  contributes one or more Parts: a multi-Part Score unpacks into all its
  Parts, anything else contributes one Part. If `instruments` is given, it
  must align with `streams` by index — each name is assigned (via
  instrument.fromString) to every Part contributed by that input."""
  if instruments is not None and len(instruments) != len(streams):
    raise ValueError(
      f"instruments length ({len(instruments)}) must match streams length "
      f"({len(streams)})"
    )

  score = stream.Score()
  for idx, s in enumerate(streams):
    parts = _extract_parts(s)
    inst_name = instruments[idx] if instruments is not None else None
    for part in parts:
      if inst_name is not None:
        part.insert(0, instrument.fromString(inst_name))
      score.insert(0, part)
  return score


def _instrument_key(part: stream.Part) -> str:
  """Return a string key identifying the part's instrument for grouping
  in sequence(). Parts with no instrument share an empty-string key.

  For percussion instruments that carry a `percMapPitch` (used to
  encode articulation on a shared class — e.g., `HiHatCymbal` with
  pmp 42 for closed vs pmp 46 for open, or `TomTom` with pmp 41 for
  low vs pmp 47 for mid), the pitch is included in the key so
  same-class-different-articulation instruments don't collide
  during grouping. Forge-music v0.3.9 — fixes the silent open→closed
  hi-hat merge in sequence() that motivated the percussion_lab
  canonical 7-part workaround.

  Non-percussion instruments (Vocalist, ElectricGuitar, etc.) carry
  no percMapPitch attribute and produce the bare class-name key
  unchanged."""
  inst = next((el for el in part.elements
               if isinstance(el, instrument.Instrument)), None)
  if inst is None:
    return ''
  base = type(inst).__name__
  pmp = getattr(inst, 'percMapPitch', None)
  if pmp is not None:
    return f"{base}:{pmp}"
  return base


def sequence(*streams: StreamLike) -> stream.Score:
  """Concatenate streams in time and return a Score.

  For each voice position across the inputs, parts are grouped by
  instrument identity. Each unique instrument at a position becomes its
  own continuous output stave; inputs whose part at that position has a
  different instrument (or no part at all) are filled with rest measures
  matching the input's bar count and time signature.

  Measures are renumbered sequentially in each output stave.

  Concretely: a song that sequences vocal choruses [harm-Piano, vocal-
  Vocalist] with an instrumental chorus [harm-Piano, solo-ElectricGuitar]
  produces three continuous staves — one each for Piano, Vocalist, and
  ElectricGuitar — with rests where each is inactive. Sections with the
  SAME instrument at a position merge into one stave; sections with
  DIFFERENT instruments at the same position split into separate staves."""
  if not streams:
    return stream.Score()

  per_input_parts = [_extract_parts(s) for s in streams]
  n_voices = max(len(parts) for parts in per_input_parts)

  # Per-input padding metadata: bar count, bar_ql, plus the actual
  # TimeSignature and Key objects from the input. The latter two are needed
  # so that when an output stave starts with padded rest measures (e.g., the
  # ElectricGuitar stave when only the third of four sections plays guitar),
  # the leading measure still declares a time signature. Without one,
  # MusicXML emits a part whose first measure has no <time>, and Verovio
  # falls back to 4/4 — the rests look wrong and bars 1..N appear empty
  # even when later measures (with their own <time>) carry actual notes.
  per_input_padding = []
  for parts in per_input_parts:
    n_bars = 0
    bar_ql = 4.0
    ts_obj = None
    ks_obj = None
    for part in parts:
      measures = list(part.getElementsByClass(stream.Measure))
      if measures:
        n_bars = len(measures)
        first_ts = next(
          (el for m in measures for el in m
           if isinstance(el, meter.TimeSignature)),
          None,
        )
        first_ks = next(
          (el for m in measures for el in m
           if isinstance(el, key.Key)),
          None,
        )
        if first_ts is not None:
          bar_ql = first_ts.barDuration.quarterLength
          ts_obj = first_ts
        if first_ks is not None:
          ks_obj = first_ks
        break
    per_input_padding.append((n_bars, bar_ql, ts_obj, ks_obj))

  score = stream.Score()
  for voice_idx in range(n_voices):
    # Group inputs' parts at this voice position by instrument identity.
    # Each unique instrument becomes its own output stave.
    groups: dict = {}
    order: list = []
    for input_idx, parts in enumerate(per_input_parts):
      if voice_idx >= len(parts):
        continue
      src_part = parts[voice_idx]
      # Local var named `inst_key` (not `key`) so the music21 `key` module
      # import remains visible — the padding branch below references key.Key.
      inst_key = _instrument_key(src_part)
      if inst_key not in groups:
        groups[inst_key] = []
        order.append(inst_key)
      groups[inst_key].append((input_idx, src_part))

    for inst_key in order:
      combined = stream.Part()
      members = groups[inst_key]
      members_by_input = {input_idx: part for input_idx, part in members}

      # Carry the instrument from the first member so the stave is labeled
      # even where inputs that don't have this instrument get padded.
      ref_part = members[0][1]
      ref_inst = next((el for el in ref_part.elements
                       if isinstance(el, instrument.Instrument)), None)
      if ref_inst is not None:
        combined.append(copy.deepcopy(ref_inst))

      next_measure_number = 1
      for input_idx, parts in enumerate(per_input_parts):
        if input_idx in members_by_input:
          src_part = members_by_input[input_idx]
          measures = list(src_part.getElementsByClass(stream.Measure))
          if measures:
            for m in measures:
              m_copy = copy.deepcopy(m)
              m_copy.number = next_measure_number
              combined.append(m_copy)
              next_measure_number += 1
          else:
            for el in src_part.elements:
              if not isinstance(el, instrument.Instrument):
                combined.append(copy.deepcopy(el))
        else:
          # Either this input lacks voice_idx entirely, or its part at
          # voice_idx has a different instrument. Pad with rest measures.
          n_bars, bar_ql, ts_obj, ks_obj = per_input_padding[input_idx]
          for j in range(n_bars):
            m = stream.Measure(number=next_measure_number)
            # Carry the input's TimeSignature (and Key) onto the very first
            # measure of the combined stave when that measure is a padded
            # rest. Without this, a stave that starts with padding has no
            # leading time-signature declaration and renders with the wrong
            # bar length under Verovio.
            is_first_in_stave = (
              j == 0 and not list(combined.getElementsByClass(stream.Measure))
            )
            if is_first_in_stave:
              if ts_obj is not None:
                m.insert(0, copy.deepcopy(ts_obj))
              if ks_obj is not None:
                m.insert(0, copy.deepcopy(ks_obj))
            m.append(note.Rest(quarterLength=bar_ql))
            combined.append(m)
            next_measure_number += 1

      score.insert(0, combined)
  return score


def voices_canonical(kp, sp=None, chp=None, ohp=None, ltp=None, mtp=None, crp=None):
  """v0.3.11 — Stack 7 percussion parts in canonical order for
  percussion_lab sections.

  Every percussion_lab section returns a Score with 7 voice positions
  (kick, snare, closed_hihat, open_hihat, low_tom, mid_tom, crash)
  regardless of which instruments actually play. Sections that don't
  play a given instrument pass None for that parameter; the helper
  builds an all-rest part at that voice position, using the bar count
  and time signature of the kick part (always required).

  The canonical layout is the contract `sequence()` requires:
  `sequence()` groups input parts by voice_idx FIRST, then by
  instrument identity within each position. Same-instrument staves
  across sections only merge correctly if every section emits that
  instrument at the same voice_idx. Without this canonical layout,
  closed_hihat at voice_idx 1 in companions and voice_idx 2 in
  gathering would render as two separate staves with 56 measures
  of combined-and-padded content instead of the intended single
  32-measure stave (this failure mode empirically verified during
  the 2026-06-06-2020-percussion-lab-seven-parts-cleanup drain;
  see that prompt's feedback file for the investigation).

  Args:
    kp: kick part (REQUIRED — bar count + time signature read here).
    sp, chp, ohp, ltp, mtp, crp: optional snare, closed_hihat,
      open_hihat, low_tom, mid_tom, crash parts. None means "this
      instrument is silent in this section" — the helper generates
      an all-rest stream.Part for that voice position matching kp's
      bar count and time signature, with the correct music21
      instrument attached (so _instrument_key groups it correctly).

  Returns:
    music21.stream.Score with 7 stacked Parts in canonical
    (kick, snare, closed_hihat, open_hihat, low_tom, mid_tom, crash)
    order. Inactive parts have rest-bars with correct instrument
    metadata.
  """
  if kp is None:
    raise ValueError(
      "voices_canonical: kp (kick part) is required — every "
      "percussion_lab section has a kick, and bar count + time "
      "signature are read from it.")

  # Derive bar count and time signature from the kick.
  kick_measures = list(kp.getElementsByClass(stream.Measure))
  n_bars = len(kick_measures)
  ts_obj = None
  if kick_measures:
    ts_obj = next(
      (el for el in kick_measures[0]
       if isinstance(el, meter.TimeSignature)),
      None,
    )
  if ts_obj is None:
    ts_obj = meter.TimeSignature('4/4')
  bar_ql = ts_obj.barDuration.quarterLength

  def _make_rest_part(inst_factory):
    """Build an all-rest Part with the same bar count + time signature
    as kp, with the canonical instrument from inst_factory."""
    part = stream.Part()
    part.append(inst_factory())
    for bar_idx in range(n_bars):
      m = stream.Measure(number=bar_idx + 1)
      if bar_idx == 0:
        m.append(copy.deepcopy(ts_obj))
      m.append(note.Rest(quarterLength=bar_ql))
      part.append(m)
    return part

  # Slot-fill: pass-through provided parts, generate all-rest for None.
  # Order matches the canonical (kick, snare, closed_hh, open_hh,
  # low_tom, mid_tom, crash) layout.
  sp_filled = sp if sp is not None else _make_rest_part(snare)
  chp_filled = chp if chp is not None else _make_rest_part(closed_hihat)
  ohp_filled = ohp if ohp is not None else _make_rest_part(open_hihat)
  ltp_filled = ltp if ltp is not None else _make_rest_part(low_tom)
  mtp_filled = mtp if mtp is not None else _make_rest_part(mid_tom)
  crp_filled = crp if crp is not None else _make_rest_part(crash_cymbal)

  return voices(
    kp, sp_filled, chp_filled, ohp_filled, ltp_filled, mtp_filled,
    crp_filled,
  )


def repeat(s: StreamLike, n: int) -> stream.Score:
  """Concatenate `s` with itself `n` times. Returns a Score for type
  uniformity (equivalent to sequence(s, s, ..., s))."""
  if n < 0:
    raise ValueError(f"n must be non-negative, got {n}")
  return sequence(*[copy.deepcopy(s) for _ in range(n)])


_PENTATONIC_INTERVALS = {
  'minor': (0, 3, 5, 7, 10),
  'major': (0, 2, 4, 7, 9),
}


def _pentatonic_pitches(
  key_or_tonic: Union[key.Key, str],
  intervals: tuple,
  octave_range: tuple[int, int],
) -> list[pitch.Pitch]:
  """Shared core for {minor,major}_pentatonic — given a tonic and the
  semitone intervals to apply, return ordered pitches across the
  requested octaves. Not exported; not pre-injected into snippets."""
  if isinstance(key_or_tonic, key.Key):
    tonic_name = key_or_tonic.tonic.name
  else:
    tonic_name = str(key_or_tonic)

  start_oct, end_oct = octave_range
  if start_oct > end_oct:
    raise ValueError(
      f"octave_range start ({start_oct}) must be <= end ({end_oct})")

  pitches: list[pitch.Pitch] = []
  for octv in range(start_oct, end_oct + 1):
    base = pitch.Pitch(f"{tonic_name}{octv}")
    for semitones in intervals:
      pitches.append(base.transpose(semitones))
  pitches.sort(key=lambda p: p.midi)
  return pitches


def minor_pentatonic(
  key_or_tonic: Union[key.Key, str],
  octave_range: tuple[int, int] = (4, 5),
  include_blue: bool = False,
) -> list[pitch.Pitch]:
  """Return minor-pentatonic scale pitches across the given octave range.

  For blues vocal/instrumental lines: use this even when the source key
  is in major mode. The minor-pentatonic-over-major-progression pattern
  is the blues convention; the function name documents the deliberate
  choice so no "mode='minor'" kwarg or defensive English is needed.

  `include_blue=True` adds the b5 (the blue note)."""
  intervals = list(_PENTATONIC_INTERVALS['minor'])
  if include_blue:
    intervals.append(6)
    intervals.sort()
  return _pentatonic_pitches(key_or_tonic, tuple(intervals), octave_range)


def major_pentatonic(
  key_or_tonic: Union[key.Key, str],
  octave_range: tuple[int, int] = (4, 5),
) -> list[pitch.Pitch]:
  """Return major-pentatonic scale pitches across the given octave range.

  Use for content that wants to track the underlying mode (most folk,
  pop, hymnody). For blues, prefer `minor_pentatonic(...)` regardless of
  the source key's mode. No `include_blue` kwarg — the blue note is a
  minor-pentatonic ornament, not a major-pentatonic one."""
  return _pentatonic_pitches(
    key_or_tonic, _PENTATONIC_INTERVALS['major'], octave_range,
  )


# v0.3.6 — velocity helper for percussion + any rhythmic content. The
# 5 named profiles cover the common dynamic shapes; int and list[int]
# patterns cover the deterministic cases. Default music21 velocity is
# 90; uniform 90 sounds like a drum machine. with_velocity is the
# fastest path to avoiding that.
#
# v0.3.8 — added mark_dynamics=True opt-in: insert visible Italian
# dynamic marks (and hairpin spanners for crescendo/decrescendo) into
# the notes' parent stream so the dynamic arc shows in the printed
# score, not just MIDI playback. Default False for back-compat and
# for pieces (e.g. Reich-style phase music) where dynamics are
# intentionally absent.

import random as _stdlib_random
from music21 import dynamics

_VELOCITY_PROFILES = {
  'human':       lambda i, n: 75 + _stdlib_random.randint(-8, 8),
  'ghost':       lambda i, n: 35 + _stdlib_random.randint(-5, 8),
  'accent':      lambda i, n: 110 + _stdlib_random.randint(-5, 10),
  'crescendo':   lambda i, n: int(40 + (90 - 40) * (i / max(n - 1, 1))),
  'decrescendo': lambda i, n: int(90 - (90 - 40) * (i / max(n - 1, 1))),
}

# Profile → nominal Italian dynamic mark (the visible representative,
# not per-note jitter). Used only when mark_dynamics=True.
_PROFILE_NOMINAL_MARK = {
  'human':  'mf',   # nominal center 75
  'ghost':  'pp',   # nominal center 35
  'accent': 'ff',   # nominal center 110
}

# Standard MIDI velocity → Italian dynamic abbreviation. Boundaries
# chosen to match typical music-engraving convention (mf is the
# neutral center around 73-85; band widths roughly equal in the
# working range).
_VELOCITY_TO_DYNAMIC = [
  # (max_velocity_inclusive, dynamic_string)
  (30,  'ppp'),
  (45,  'pp'),
  (60,  'p'),
  (72,  'mp'),
  (85,  'mf'),
  (100, 'f'),
  (115, 'ff'),
  (127, 'fff'),
]


def _velocity_to_dynamic_mark(velocity):
  """Map a MIDI velocity (1-127) to its Italian dynamic abbreviation."""
  for max_v, mark in _VELOCITY_TO_DYNAMIC:
    if velocity <= max_v:
      return mark
  return 'fff'  # safety; clamped values shouldn't reach here


def _insert_dynamic_at_note(target_note, mark):
  """Insert a music21.dynamics.Dynamic at target_note's offset in its
  parent stream (activeSite). Skip silently when activeSite is None."""
  site = target_note.activeSite
  if site is None:
    return
  d = dynamics.Dynamic(mark)
  site.insert(target_note.offset, d)


def with_velocity(notes, pattern, mark_dynamics=False):
  """Apply velocity values to a sequence of Note objects per a pattern.

  Mutates each note's `.volume.velocity` in place and returns the list
  for chaining. Rests in the sequence are skipped.

  Patterns:
    'human'       — small random variation around 75 (±8). Default for
                    realistic-feel drumming.
    'ghost'       — quiet (~35), for ghost notes between accents.
    'accent'      — loud (~110), for hits that punch.
    'crescendo'   — linear ramp from 40 to 90 across the sequence.
    'decrescendo' — linear ramp from 90 to 40.
    int (1-127)   — uniform value across all notes.
    list of ints  — cyclic pattern, e.g. [100, 60, 80, 60].

  mark_dynamics: When True, insert visible score dynamics in addition
                 to setting MIDI velocity (default False for back-compat
                 and respect for pieces where dynamics are intentionally
                 absent, e.g. Reich-style phase music).

                 - int and named-profile (human/ghost/accent) patterns
                   insert ONE Dynamic mark at the first non-rest note,
                   representing the section's overall level.
                 - 'crescendo' / 'decrescendo' insert a hairpin
                   (dynamics.Crescendo / dynamics.Diminuendo) spanner
                   plus bracketing Dynamics ('p'/'f' for crescendo;
                   'f'/'p' for decrescendo).
                 - list patterns SKIP dynamic insertion (per-note
                   alternation is too granular to mark cleanly; use
                   per-note articulation helpers for accents).

                 Insertion targets each note's `.activeSite` (the
                 enclosing Measure). Notes whose activeSite is None
                 are skipped silently — call with_velocity AFTER
                 adding notes to their measures for marks to land.

  Returns: notes (same list reference, mutated)."""
  if isinstance(pattern, bool):
    # Python booleans are ints; guard so True/False don't accidentally
    # become uniform velocity 1 / 0.
    raise ValueError(f"velocity pattern must be int (1-127), list, or named profile; got bool {pattern!r}")

  non_rest_notes = [n for n in notes if not isinstance(n, note.Rest)]

  if isinstance(pattern, int):
    clamped = max(1, min(127, pattern))
    for n in non_rest_notes:
      n.volume.velocity = clamped
    if mark_dynamics and non_rest_notes:
      _insert_dynamic_at_note(non_rest_notes[0], _velocity_to_dynamic_mark(clamped))
    return notes

  if isinstance(pattern, list):
    if not pattern:
      raise ValueError("velocity pattern list must be non-empty")
    for i, n in enumerate(non_rest_notes):
      n.volume.velocity = max(1, min(127, pattern[i % len(pattern)]))
    # List patterns deliberately SKIP dynamic insertion — per-note
    # alternation is too granular to mark cleanly without clutter.
    return notes

  if pattern not in _VELOCITY_PROFILES:
    raise ValueError(
      f"unknown velocity pattern {pattern!r}; expected one of "
      f"{list(_VELOCITY_PROFILES)} or int 1-127 or list[int]"
    )

  profile_fn = _VELOCITY_PROFILES[pattern]
  n_total = len(non_rest_notes)
  for i, n in enumerate(non_rest_notes):
    v = profile_fn(i, n_total)
    n.volume.velocity = max(1, min(127, v))

  if mark_dynamics and non_rest_notes:
    if pattern in ('crescendo', 'decrescendo'):
      # Bracketing Dynamics + a hairpin Spanner across first..last.
      if pattern == 'crescendo':
        _insert_dynamic_at_note(non_rest_notes[0], 'p')
        _insert_dynamic_at_note(non_rest_notes[-1], 'f')
        hairpin = dynamics.Crescendo()
      else:
        _insert_dynamic_at_note(non_rest_notes[0], 'f')
        _insert_dynamic_at_note(non_rest_notes[-1], 'p')
        hairpin = dynamics.Diminuendo()
      hairpin.addSpannedElements([non_rest_notes[0], non_rest_notes[-1]])
      # Spanner lives at the first note's stream; insert at first note's offset.
      first_site = non_rest_notes[0].activeSite
      if first_site is not None:
        first_site.insert(non_rest_notes[0].offset, hairpin)
    else:
      _insert_dynamic_at_note(non_rest_notes[0], _PROFILE_NOMINAL_MARK[pattern])

  return notes


# v0.3.6 Phase B/C — percussion instrument factories. music21 has
# ONE HiHatCymbal class; open vs closed vs pedal articulation is
# encoded as the GM percussion note number on channel 10 (the
# `percMapPitch` attribute), not as separate classes or midi-program
# changes. Same shape for cymbals + toms.
#
# v0.3.7 — fix MuseScore rendering for multi-part percussion scores.
# music21's MusicXML exporter enforces channel uniqueness per Score
# (see m21ToXml.py:2801-2810): the FIRST percussion instrument keeps
# midiChannel=9 (→ <midi-channel>10</midi-channel>), but subsequent
# parts with midiChannel=9 collide and get reassigned via
# autoAssignMidiChannel() to channels 1, 2, 3... — the melodic
# channels, which MuseScore renders as Piano-default 5-line treble
# staves instead of percussion staves. _force_perc_channel patches
# autoAssignMidiChannel on each instance to return 9 unconditionally,
# so every percussion part ends up on GM channel 10.
#
# percMapPitch values are unchanged from v0.3.6 — the MIDI export
# (which GarageBand reads) was already correct in v0.3.6; we only
# fix the MusicXML channel assignment for MuseScore visual rendering.

def _force_perc_channel(inst, name, abbrev):
  """Lock midiChannel=9 (GM channel 10) by overriding autoAssignMidiChannel
  on this instance, and override the displayed instrument name. Used by
  every percussion factory so MuseScore renders all percussion parts
  as percussion staves uniformly."""
  inst.midiChannel = 9
  inst.autoAssignMidiChannel = lambda usedChannels=None: 9
  inst.instrumentName = name
  inst.instrumentAbbreviation = abbrev
  return inst


def kick():
  """Kick drum (bass drum). GM note 36 (Bass Drum 1) on channel 10.
  music21's default instrumentName for BassDrum is 'Bass Drum'; the
  factory overrides to 'Kick' for kit-conventional labeling."""
  inst = instrument.BassDrum()
  # percMapPitch left at music21's default (35), which serializes to
  # <midi-unpitched>36</midi-unpitched> = GM Bass Drum 1.
  return _force_perc_channel(inst, 'Kick', 'K')


def closed_hihat():
  """Closed hi-hat (short "ts" sound). GM note 42 on channel 10."""
  inst = instrument.HiHatCymbal()
  inst.percMapPitch = 42
  return _force_perc_channel(inst, 'Closed Hi-Hat', 'CHH')


def open_hihat():
  """Open hi-hat (longer "tsh" sound). GM note 46 on channel 10."""
  inst = instrument.HiHatCymbal()
  inst.percMapPitch = 46
  return _force_perc_channel(inst, 'Open Hi-Hat', 'OHH')


def pedal_hihat():
  """Foot-pedal hi-hat (chick). GM note 44 on channel 10."""
  inst = instrument.HiHatCymbal()
  inst.percMapPitch = 44
  return _force_perc_channel(inst, 'Pedal Hi-Hat', 'PHH')


def low_tom():
  """Low (floor) tom. GM note 41 on channel 10. music21 has one
  TomTom class; the three tom variants in this lib differ only in
  percMapPitch (41 / 47 / 50)."""
  inst = instrument.TomTom()
  inst.percMapPitch = 41
  return _force_perc_channel(inst, 'Low Tom', 'LT')


def mid_tom():
  """Mid tom. GM note 47 on channel 10."""
  inst = instrument.TomTom()
  inst.percMapPitch = 47
  return _force_perc_channel(inst, 'Mid Tom', 'MT')


def high_tom():
  """High tom. GM note 50 on channel 10."""
  inst = instrument.TomTom()
  inst.percMapPitch = 50
  return _force_perc_channel(inst, 'High Tom', 'HT')


def crash_cymbal():
  """Crash cymbal 1. GM note 49 on channel 10."""
  inst = instrument.CrashCymbals()
  inst.percMapPitch = 49
  return _force_perc_channel(inst, 'Crash Cymbal', 'CR')


def ride_cymbal():
  """Ride cymbal 1. GM note 51 on channel 10."""
  inst = instrument.RideCymbals()
  inst.percMapPitch = 51
  return _force_perc_channel(inst, 'Ride Cymbal', 'RD')


# v2-spike Phase 1 — high-level chip primitives for E-- recipes (per
# v2-spec §16). play_at_beats lets a cohort author write `Call
# [[play_at_beats]] with instrument=kick(), beats=[1, 3]` and get back
# a music21 Part whose MIDI export lands at the correct channel-10
# drum slot (kick=35, snare=38, etc.) without relying on the
# serialization.py percMapPitch normalization downstream.

def play_at_beats(instrument, beats):
  """Build a music21 Part with one quarter-note hit per beat position.
  `beats` is 1-INDEXED (beat 1 = first beat of the bar = offset 0.0;
  there is no beat 0). For 0-indexed positions, multi-bar patterns,
  or non-quarter-note durations, use [[play_at_offsets]] instead.

  Args:
    instrument: a music21 Instrument (typically from one of the percussion
      factories above — kick(), snare(), closed_hihat(), etc.). When
      the instrument has a `percMapPitch` attribute, every note's
      pitch.midi is set to that value so streamToMidiFile emits the
      correct drum slot on channel 10 (per the v0.2.159 lesson: music21
      uses each NOTE's spelled pitch, not the Part instrument's
      percMapPitch). For non-percussion instruments without percMapPitch,
      notes default to C4 (spec doesn't pin this; cohort can override
      via more specialized chips in V2.1).
    beats: a list of beat positions, 1-indexed (beat 1 = first beat of
      the bar = offset 0.0). Floats are supported for sub-beat
      positions ([1, 1.5, 2, 2.5] is straight eighths). An empty list
      returns a Part with just the instrument attached.

  Returns:
    music21.stream.Part with the instrument inserted at offset 0 and
    one quarterLength=1 Note per beat position. Note pitch normalized
    for percussion as described above.

  Raises:
    ValueError: if any beat is < 1 (1-indexed convention). The error
      message points cohort at [[play_at_offsets]] which IS 0-indexed.
      Pre-v0.2.200 the catalog's first-paragraph introspection didn't
      surface the 1-indexed convention, and the LLM happily generated
      `beats=[0]` (programmer-natural 0-index). That produced
      offset=-1, music21 raised a cryptic StreamException about a note
      with start -1.0 not fitting any measure, and cohort hit a
      traceback they couldn't act on.
  """
  for beat in beats:
    if float(beat) < 1:
      raise ValueError(
        f"play_at_beats: beats are 1-indexed (beat 1 = first beat of "
        f"the bar = offset 0.0); got beat={beat!r} which is < 1. "
        f"Either use beats=[1, ...] for the first beat, or switch to "
        f"`Call [[play_at_offsets]] with instrument=..., offsets=[0, ...]` "
        f"for 0-indexed offsets (offset 0 = first beat)."
      )
  part = stream.Part()
  part.insert(0, instrument)
  pmp = getattr(instrument, 'percMapPitch', None)
  for beat in beats:
    offset = float(beat) - 1.0
    n = note.Note('C4', quarterLength=1.0)
    if pmp is not None:
      try:
        n.pitch.midi = pmp
      except Exception:
        pass
    part.insert(offset, n)
  return part


def show_score(score):
  """Side-effect chip — surfaces a Score for the plugin to render in
  Forge Output. For the spike this is a passthrough: the plugin's
  auto-render fallback (v2-spec §15.4) catches Score returns and
  renders them, so explicit `[[show_score]]` is for V2.1's multi-
  destination orchestration. Returns the input unchanged so cohort
  recipes can write `Let s = build_score. [[show_score]] s. Return s.`
  without losing the value."""
  return score


def sequence_list(sections):
  """v2 — composition chip. E-- has no `*args` syntax, so `sequence(*xs)`
  isn't callable directly from E--. `[[sequence_list]] with sections=[s1, s2, ...]`
  unpacks the list and forwards to the V1 `sequence` builder. Returns the
  concatenated Score with sequentially-renumbered measures + same-instrument
  staves merged across sections (per sequence's existing contract)."""
  return sequence(*sections)


def voices_list(sections):
  """v2 — composition chip. Parallel to `sequence_list` for `voices(*streams)`.
  E-- has no `*args` syntax, so `voices(*xs)` isn't callable directly from E--.
  `[[voices_list]] with sections=[s1, s2, ...]` unpacks the list and forwards
  to the V1 `voices` builder. Returns a Score with the input streams overlaid
  in parallel (each stream gets its own staff, durations preserved)."""
  return voices(*sections)


def bar_list(items, time_signature=None, number=None):
  """v2 — composition chip. Parallel to `sequence_list`/`voices_list` for
  `bar(*items, time_signature=None, number=None)`. V2 Recipe is kwarg-only;
  variadic-positional `*items` isn't directly expressible. Pass the items
  as a list:
      Call [[bar_list]] with items=[n1, n2, n3], time_signature=ts.
  Equivalent to `bar(n1, n2, n3, time_signature=ts)`."""
  return bar(*items, time_signature=time_signature, number=number)


def play_at_offsets(
    instrument,
    offsets,
    duration=0.25,
    bars=4,
    time_signature='4/4',
    tempo_bpm=96,
    velocity=None,
    mark_dynamics=False,
):
  """v2 — composite percussion-part chip for the percussion_lab section
  shape. Builds a music21 Part with `bars` Measure objects, each
  carrying hits at the given offsets (in quarterLengths within the
  bar, 0-indexed: beat 1 = offset 0.0). Measure 1 carries the
  TimeSignature + MetronomeMark; subsequent bars inherit.

  Args:
    instrument: percussion factory output (kick(), snare(), etc.) —
      Part-level instrument for channel-10 routing.
    offsets: either
      (a) flat list [0, 2] — same pattern every bar, OR
      (b) list of lists [[0, 2], [0, 1, 2]] — per-bar variation,
          cycled when `bars` exceeds `len(offsets)`.
    duration: per-hit quarterLength (default 0.25 = 16th note).
    bars: total bars in this Part.
    time_signature: e.g. '4/4'. Inserted on measure 1.
    tempo_bpm: MetronomeMark BPM on measure 1.
    velocity: int (1-127) for fixed velocity, OR string profile name
      ('human', 'crescendo', 'decrescendo', etc.) — wraps with_velocity.
      None = leave velocities at music21 defaults.
    mark_dynamics: when True and velocity is set, insert a visible
      dynamic mark on the first note (per v0.3.8 with_velocity contract).

  Returns:
    music21.stream.Part with the instrument + bars measures of hits.
    Notes' pitch.midi normalized to instrument.percMapPitch so MIDI
    export lands on the correct channel-10 drum slot (per v0.2.159).
  """
  # Normalize offsets to a per-bar list (list of lists).
  if not offsets:
    bar_patterns = [[]] * bars
  else:
    is_nested = isinstance(offsets[0], (list, tuple))
    if is_nested:
      # Cycle the pattern if bars > len(offsets); truncate if bars < len.
      bar_patterns = [
        list(offsets[i % len(offsets)]) for i in range(bars)
      ]
    else:
      bar_patterns = [list(offsets)] * bars

  ts_obj = meter.TimeSignature(time_signature)
  mm_obj = tempo.MetronomeMark(number=tempo_bpm)
  bar_ql = ts_obj.barDuration.quarterLength
  pmp = getattr(instrument, 'percMapPitch', None)

  part = stream.Part()
  part.append(instrument)
  built_notes = []
  for bar_idx in range(bars):
    m = stream.Measure(number=bar_idx + 1)
    if bar_idx == 0:
      m.append(copy.deepcopy(ts_obj))
      m.append(copy.deepcopy(mm_obj))
    cursor = 0.0
    sorted_offs = sorted(bar_patterns[bar_idx])
    for off in sorted_offs:
      if off > cursor:
        m.append(note.Rest(quarterLength=off - cursor))
        cursor = off
      n = note.Note('C4', quarterLength=duration)
      if pmp is not None:
        try:
          n.pitch.midi = pmp
        except Exception:
          pass
      m.append(n)
      built_notes.append(n)
      cursor += duration
    if cursor < bar_ql:
      m.append(note.Rest(quarterLength=bar_ql - cursor))
    part.append(m)

  # Velocity post-processing.
  if velocity is not None and built_notes:
    with_velocity(built_notes, velocity, mark_dynamics=mark_dynamics)

  return part


def snare():
  """Snare drum. GM note 38 (Acoustic Snare) on channel 10. music21's
  default instrumentName for SnareDrum is 'Snare Drum'; factory keeps
  that but forces channel 10 for multi-part percussion scores."""
  inst = instrument.SnareDrum()
  # percMapPitch left at music21's default (38).
  return _force_perc_channel(inst, 'Snare', 'S')


def _coerce_to_part(s: StreamLike) -> stream.Part:
  """Convert a single-voice StreamLike input to a Part (deepcopied so callers
  can reuse the input). Multi-Part Scores are handled upstream by
  _extract_parts and never reach here."""
  if isinstance(s, stream.Score):
    parts = list(s.getElementsByClass(stream.Part))
    if len(parts) == 1:
      return copy.deepcopy(parts[0])
    part = stream.Part()
    for el in s.elements:
      part.append(copy.deepcopy(el))
    return part
  if isinstance(s, stream.Part):
    return copy.deepcopy(s)
  if isinstance(s, stream.Measure):
    part = stream.Part()
    part.append(copy.deepcopy(s))
    return part
  part = stream.Part()
  for el in s.elements:
    part.append(copy.deepcopy(el))
  return part


def _extract_parts(s: StreamLike) -> list[stream.Part]:
  """Return the constituent Parts of a stream. A Score yields its Parts;
  anything else is treated as a single Part (coerced)."""
  if isinstance(s, stream.Score):
    parts = list(s.getElementsByClass(stream.Part))
    if parts:
      return [copy.deepcopy(p) for p in parts]
  return [_coerce_to_part(s)]


# v0.3.x — kit-notation rendering. Folds multiple percussion Parts into a
# single staff with two voices (stems-up for hands, stems-down for kick),
# per the v0.2.143 cohort feature. Independent of MIDI export: the
# canonical multi-Part Score remains the source of truth for playback;
# `to_kit_notation` produces a *visual* alternative that renders compact
# (single 5-line staff with kit conventions) for drummer-readable
# notation.
#
# Per the v0.2.143 prompt §3.2 + Hal Leonard Drum Method reference, the
# pitch + notehead mapping is:
#
#   Instrument     music21 pitch  Voice  Notehead   Staff position
#   Kick           B1             2 (↓)  normal     space below staff
#   Snare          E2             1 (↑)  normal     middle line
#   Closed hi-hat  G2             1 (↑)  x          above staff
#   Open hi-hat    G2             1 (↑)  circle-x   above staff
#   Pedal hi-hat   D2             2 (↓)  x          space below middle
#   Low tom        F2             1 (↑)  normal     2nd line up
#   Mid tom        A2             1 (↑)  normal     3rd space up
#   High tom       C3             1 (↑)  normal     above staff
#   Crash          A2             1 (↑)  x          above staff
#   Ride           F3             1 (↑)  x          above staff

# Pitch + notehead + voice spec keyed by music21 Instrument class name.
# Looked up via type(inst).__name__ on each Note's getInstrument() return.
# The mapping uses percMapPitch where it disambiguates within a single
# music21 class (HiHatCymbal: closed/open/pedal share class but differ
# on percMapPitch 42/46/44; same for cymbals if needed).
_KIT_VOICE_HANDS = 1
_KIT_VOICE_FEET = 2

# Map (m21_class_name, percMapPitch_or_None) → (display_position, voice, notehead).
#
# v0.2.145 — values are DISPLAY POSITIONS for note.Unpitched (not real
# pitches). Pre-v0.2.145 used note.Note with literal pitches (B1, E2,
# G2 etc.) which Verovio rendered at their absolute pitch positions
# below the staff. Driver's spike on 2026-06-26 confirmed:
#   ✗ Kit notes positioned by literal pitch, not kit-convention staff
#     position.
#   ✗ Voice stem directions overridden by Verovio's auto-stemming for
#     low-pitched notes.
#
# Migrating to note.Unpitched with displayName='G5'-style display
# positions makes Verovio honor the position via <display-step> +
# <display-octave> tags per MusicXML standard. Positions below follow
# the Hal Leonard Drum Method / MuseScore-Finale default convention
# for a 5-line staff with percussion clef (treble-clef-conceptual).
_KIT_NOTATION_MAP = {
  # Kick — voice 2 stems down. Just below the staff.
  ('BassDrum', None): ('F4', _KIT_VOICE_FEET, 'normal'),
  # Snare — voice 1, middle (3rd space).
  ('SnareDrum', None): ('C5', _KIT_VOICE_HANDS, 'normal'),
  # Hi-hats — closed/open/pedal share HiHatCymbal class, differ on
  # percMapPitch (42 / 46 / 44 per the lib.py factories). Closed +
  # open above staff (first leger line up); pedal below staff.
  ('HiHatCymbal', 42): ('G5', _KIT_VOICE_HANDS, 'x'),         # closed
  ('HiHatCymbal', 46): ('G5', _KIT_VOICE_HANDS, 'circle-x'),  # open
  ('HiHatCymbal', 44): ('D4', _KIT_VOICE_FEET, 'x'),          # pedal
  # Catch-all hi-hat (unknown percMapPitch) → treat as closed.
  ('HiHatCymbal', None): ('G5', _KIT_VOICE_HANDS, 'x'),
  # Toms — low (3rd space from bottom), mid (4th line), high (top
  # space). Variants differ only on percMapPitch (41/47/50).
  ('TomTom', 41): ('A4', _KIT_VOICE_HANDS, 'normal'),  # low
  ('TomTom', 47): ('D5', _KIT_VOICE_HANDS, 'normal'),  # mid
  ('TomTom', 50): ('E5', _KIT_VOICE_HANDS, 'normal'),  # high
  ('TomTom', None): ('D5', _KIT_VOICE_HANDS, 'normal'),  # fallback (mid)
  # Cymbals — crash + ride get X-noteheads above staff. Crash sits
  # higher than hi-hat per kit convention. Ride on top line.
  ('CrashCymbals', None): ('A5', _KIT_VOICE_HANDS, 'x'),
  ('RideCymbals', None): ('F5', _KIT_VOICE_HANDS, 'x'),
}


def _kit_lookup(inst):
  """Return (display_position, voice, notehead) for a percussion
  instrument, or None if the instrument isn't a recognized percussion
  class. Falls back through (class_name, percMapPitch) → (class_name,
  None) so an unrecognized percMapPitch within a known class still
  gets a sane default.

  v0.2.145 — first value is now a DISPLAY POSITION (e.g. 'C5' = snare
  middle line) for note.Unpitched.displayName, not a literal pitch.
  """
  if inst is None:
    return None
  cls = type(inst).__name__
  pmp = getattr(inst, 'percMapPitch', None)
  if (cls, pmp) in _KIT_NOTATION_MAP:
    return _KIT_NOTATION_MAP[(cls, pmp)]
  if (cls, None) in _KIT_NOTATION_MAP:
    return _KIT_NOTATION_MAP[(cls, None)]
  return None


def has_percussion(score: stream.Score) -> bool:
  """v0.3.x — true iff the score contains at least one Part whose
  Instrument is an UnpitchedPercussion subclass (or one of the
  recognized percussion classes from lib.py's factories).

  Used by the plugin to decide whether to show the kit-notation toggle
  button in the Forge Output pane. Piano-only / melodic-only scores
  return False; the toggle stays hidden.
  """
  if not isinstance(score, stream.Score):
    return False
  for part in score.getElementsByClass(stream.Part):
    inst = part.getInstrument(returnDefault=False)
    if inst is None:
      continue
    if _kit_lookup(inst) is not None:
      return True
    # Also recognize generic UnpitchedPercussion subclasses we didn't
    # explicitly enumerate (defensive forward-compat).
    if isinstance(inst, instrument.UnpitchedPercussion):
      return True
  return False


def to_kit_notation(score: stream.Score) -> stream.Score:
  """v0.3.x — fold percussion Parts of a Score into a single staff with
  two voices (stems-up for hands, stems-down for kick), preserving
  music21 note IDs and per-note Instrument identity.

  Non-percussion Parts pass through unchanged. Returns a NEW Score; does
  not mutate the input.

  Per v0.2.143 cohort feature. The kit Part is a *visual* fold; the
  per-note Instrument references on the merged notes preserve channel-10
  routing so MIDI export from the kit Score is equivalent to MIDI export
  from the original canonical Score.

  Algorithm:
  1. Walk score.parts. Split into percussion vs non-percussion lists.
  2. If no percussion: return a deep-copy of the input Score (no work).
  3. Build a kit Part with PercussionClef + two Voices. Map each
     percussion-Part note via _KIT_NOTATION_MAP → kit pitch + voice +
     notehead.
  4. Preserve note.id (drives the plugin's click-to-play SVG → note
     map) and the original Instrument reference (via note.editorial so
     MIDI export still walks per-instrument).
  5. Stems: voice 1 = up, voice 2 = down. Noteheads applied per the
     mapping table.
  6. Assemble output Score: [non-percussion parts in original order +
     kit Part at the position of the first original percussion Part].
  """
  if not isinstance(score, stream.Score):
    return score

  output = stream.Score()
  # Copy score-level metadata so engraving (title, composer) survives.
  if score.metadata is not None:
    output.metadata = copy.deepcopy(score.metadata)

  parts = list(score.getElementsByClass(stream.Part))
  if not parts:
    return output

  percussion_parts: list[stream.Part] = []
  non_percussion_parts: list[stream.Part] = []
  first_perc_index: int | None = None
  for i, part in enumerate(parts):
    inst = part.getInstrument(returnDefault=False)
    is_perc = (
      inst is not None
      and (_kit_lookup(inst) is not None
           or isinstance(inst, instrument.UnpitchedPercussion))
    )
    if is_perc:
      percussion_parts.append(part)
      if first_perc_index is None:
        first_perc_index = i
    else:
      non_percussion_parts.append(part)

  if not percussion_parts:
    # Percussion-less score: deep-copy parts through; non-mutating.
    for p in parts:
      output.append(copy.deepcopy(p))
    return output

  # Build the kit Part.
  kit_part = stream.Part()
  # Use UnpitchedPercussion as a generic Part-level instrument; per-note
  # Instrument references are preserved via note.editorial so MIDI walks
  # see the actual kick/snare/etc.
  kit_inst = instrument.UnpitchedPercussion()
  _force_perc_channel(kit_inst, 'Kit', 'Kit')
  kit_part.insert(0, kit_inst)
  # Percussion clef so Verovio renders the 5-line staff with the
  # percussion convention (no pitch, just staff positions).
  kit_part.insert(0, clef.PercussionClef())

  # v0.2.153 — measure-preserving build. Pre-v0.2.153 the kit fold
  # inserted notes into flat Voices on the kit Part, losing the
  # canonical Score's Measure structure + TimeSignature. music21
  # serialized that flat stream to MusicXML without bar boundaries,
  # leaving Verovio to guess barlines from its own heuristics — which
  # split each canonical bar into multiple kit bars AND dropped some
  # notes from MIDI playback (driver smoke against v0.2.152 saw kit
  # bar 1 = "drum, silent drum" where multi-staff bar 1 = "drum,
  # silence, drum, silence"). Walking measure-by-measure and rebuilding
  # voices INSIDE each measure preserves the source's bar layout and
  # restores 1:1 MIDI playback.
  template_part = percussion_parts[0]
  template_measures = list(template_part.getElementsByClass(stream.Measure))

  if not template_measures:
    # Fallback: hand-built test snippets that lack Measure structure.
    # The flat-fold path at the bottom of this function (gated on this
    # `template_measures` check) runs in that case.
    pass
  else:
    from music21 import tempo as _tempo
    for tmpl in template_measures:
      kit_measure = stream.Measure(number=tmpl.number)
      # Carry over TimeSignature so Verovio + MusicXML know the bar
      # length. Without this, music21 emits unmeasured content and
      # downstream renderers guess bar boundaries.
      if tmpl.timeSignature is not None:
        kit_measure.timeSignature = copy.deepcopy(tmpl.timeSignature)
      # Same for KeySignature (no-op for unpitched percussion but
      # cheap insurance for mixed pieces).
      if tmpl.keySignature is not None:
        kit_measure.keySignature = copy.deepcopy(tmpl.keySignature)
      # v0.2.160 — also carry over any MetronomeMark (tempo) attached
      # to this source measure. Without this, kit_xml defaults to
      # Verovio's ~120 BPM while multi-staff plays at the source's
      # actual tempo (e.g., murmuration's 96 BPM). The mismatch makes
      # the kit-mode highlight-tracking scale drift bar-by-bar — by
      # bar 5 the highlight lags / leads the audio by enough that the
      # driver perceives notes as "missing" in kit even though the
      # shared multi-staff MIDI is playing them correctly.
      for mm in tmpl.getElementsByClass(_tempo.MetronomeMark):
        kit_measure.insert(mm.offset, copy.deepcopy(mm))
      v_hands = stream.Voice()
      v_hands.id = '1'
      v_feet = stream.Voice()
      v_feet.id = '2'
      for src_part in percussion_parts:
        src_inst = src_part.getInstrument(returnDefault=False)
        spec = _kit_lookup(src_inst)
        if spec is None:
          spec = ('C5', _KIT_VOICE_HANDS, 'normal')
        disp, voice_id, notehead = spec
        # Locate this part's measure with the matching number. Some
        # source parts may not have a measure at every number (e.g.,
        # silence-only measures sometimes omitted); skip gracefully.
        src_measure = src_part.measure(tmpl.number)
        if src_measure is None:
          continue
        for src_note in src_measure.recurse().notes:
          new_note = note.Unpitched(displayName=disp)
          new_note.quarterLength = src_note.quarterLength
          if src_note.id is not None:
            new_note.id = src_note.id
          new_note.storedInstrument = src_inst
          if 'misc' not in new_note.editorial:
            new_note.editorial.misc = {}
          new_note.editorial.misc['forge_source_instrument'] = src_inst
          if voice_id == _KIT_VOICE_HANDS:
            new_note.stemDirection = 'up'
          else:
            new_note.stemDirection = 'down'
          if notehead != 'normal':
            new_note.notehead = notehead
          if src_note.volume is not None:
            new_note.volume = copy.deepcopy(src_note.volume)
          offset_in_measure = src_note.getOffsetInHierarchy(src_measure)
          if voice_id == _KIT_VOICE_HANDS:
            v_hands.insert(offset_in_measure, new_note)
          else:
            v_feet.insert(offset_in_measure, new_note)
      kit_measure.insert(0, v_hands)
      kit_measure.insert(0, v_feet)
      kit_part.append(kit_measure)

  # v0.2.153 — flat-fold fallback path. Runs ONLY when the source
  # percussion Parts lack Measure structure (typically hand-built test
  # snippets). The measure-preserving path above is the normal route
  # for cohort pieces. Same per-note logic as the measure-preserving
  # path; just walks notes flat instead of grouping by measure.
  if not template_measures:
    voice_hands = stream.Voice()
    voice_hands.id = '1'
    voice_feet = stream.Voice()
    voice_feet.id = '2'
    for src_part in percussion_parts:
      src_inst = src_part.getInstrument(returnDefault=False)
      src_spec = _kit_lookup(src_inst)
      if src_spec is None:
        src_spec = ('C5', _KIT_VOICE_HANDS, 'normal')
      display_pos, voice_id, notehead_type = src_spec
      for src_note in src_part.recurse().notes:
        new_note = note.Unpitched(displayName=display_pos)
        new_note.quarterLength = src_note.quarterLength
        if src_note.id is not None:
          new_note.id = src_note.id
        new_note.storedInstrument = src_inst
        if 'misc' not in new_note.editorial:
          new_note.editorial.misc = {}
        new_note.editorial.misc['forge_source_instrument'] = src_inst
        if voice_id == _KIT_VOICE_HANDS:
          new_note.stemDirection = 'up'
        else:
          new_note.stemDirection = 'down'
        if notehead_type != 'normal':
          new_note.notehead = notehead_type
        if src_note.volume is not None:
          new_note.volume = copy.deepcopy(src_note.volume)
        offset = src_note.getOffsetInHierarchy(src_part)
        if voice_id == _KIT_VOICE_HANDS:
          voice_hands.insert(offset, new_note)
        else:
          voice_feet.insert(offset, new_note)
    kit_part.insert(0, voice_hands)
    kit_part.insert(0, voice_feet)

  # Assemble output Score: non-percussion parts in original order +
  # kit Part inserted at the first percussion Part's original index.
  insert_idx = first_perc_index if first_perc_index is not None else len(non_percussion_parts)
  for i, p in enumerate(non_percussion_parts):
    if i == insert_idx:
      output.append(kit_part)
    output.append(copy.deepcopy(p))
  if insert_idx >= len(non_percussion_parts):
    output.append(kit_part)

  return output


# ---------------------------------------------------------------------------
# v0.7.0 — forge-music library notes promoted from engineer-mode vault notes
# (per drain 2026-07-01-1800). The 8 functions below were vault `.md` files
# with `edit_mode: python` + stub Recipe; they are now first-class library
# notes callable from V2 Recipes via `Call [[name]] with k=v.` (the wikilink
# resolves to a LibraryNoteView in the plugin).
#
# Each retains the music21 semantics it had as an engineer-mode note.
# Cohort callers (song.md, chorus.md, solo_chorus.md, loom.md) now invoke
# these directly from their Python facets rather than via
# context.compute("name", ...).
# ---------------------------------------------------------------------------


DEFAULT_BLUES_PROGRESSION = ["I", "I", "I", "I", "IV", "IV", "I", "I", "V", "IV", "I", "V"]
"""Standard 12-bar blues chord progression as roman numerals.
Embedded default for `form()` so the function is self-contained — the
prior vault stub fetched this from `twelve_bar_blues_progression` data
note; cohort can still override via the `progression` kwarg if a
different shape is needed."""


def form(*, key_name="E", mode_name="major", tempo_bpm=70,
         ts_str="12/8", progression=None):
  """The harmonic skeleton of a standard 12-bar blues form.

  Twelve bars in 12/8, slow (around 70 BPM, eighth-note triplet feel).
  Roman-numeral progression resolves to concrete chords via
  music21.roman in the given key. Returns a Score with chord symbols
  and full triads, no melodic content — the tonal frame everything
  else hangs from. Use Piano for this.

  Defaults to E major + the standard 12-bar progression
  (DEFAULT_BLUES_PROGRESSION). Pass `progression=[...]` to override.
  """
  import copy as _copy
  prog = list(progression) if progression is not None else list(DEFAULT_BLUES_PROGRESSION)
  k = key.Key(key_name, mode_name)
  ts = meter.TimeSignature(ts_str)
  bar_ql = ts.barDuration.quarterLength
  mm = tempo.MetronomeMark(number=tempo_bpm, referent=duration.Duration(type="quarter", dots=1))

  part = stream.Part()
  part.append(instrument.Piano())

  for i, numeral in enumerate(prog):
    m = stream.Measure(number=i + 1)
    if i == 0:
      m.append(_copy.deepcopy(k))
      m.append(_copy.deepcopy(ts))
      m.append(_copy.deepcopy(mm))
    rn = roman.RomanNumeral(numeral, k)
    root_name = rn.root().name
    quality_map = {
      "major": "", "minor": "m",
      "diminished": "dim", "augmented": "aug",
      "dominant-seventh": "7", "major-seventh": "maj7",
      "minor-seventh": "m7",
    }
    suffix = quality_map.get(rn.quality, "")
    cs_figure = root_name + suffix
    cs = harmony.ChordSymbol(cs_figure)
    m.insert(0, cs)
    c = chord.Chord(list(rn.pitches), quarterLength=bar_ql)
    m.insert(0, c)
    part.append(m)

  score = stream.Score()
  score.append(part)
  return score


def drum_chorus(*, profile="standard"):
  """One 12-bar drum chorus parameterized by a profile name (`'sparse'`,
  `'standard'`, or `'driving'`). Used by `song.md` to give the 4-chorus
  arc audible variety: sparse intro → standard mid → driving solo →
  standard return. 12 bars in 12/8."""
  import copy as _copy
  ts = meter.TimeSignature("12/8")
  bar_ql = ts.barDuration.quarterLength
  eighth = 0.5
  BEAT_1, BEAT_2, BEAT_3, BEAT_4 = 0.0, 1.5, 3.0, 4.5

  def _drum_bar(hit_specs, bar_idx, attach_metadata):
    m = stream.Measure(number=bar_idx + 1)
    if attach_metadata:
      m.append(ts)
    notes_added = []
    cursor = 0.0
    for off, dur in sorted(hit_specs):
      gap = off - cursor
      if gap > 0:
        m.append(note.Rest(quarterLength=gap))
        cursor += gap
      n = note.Note("C4", quarterLength=dur)
      m.append(n)
      notes_added.append(n)
      cursor += dur
    remaining = bar_ql - cursor
    if remaining > 0:
      m.append(note.Rest(quarterLength=remaining))
    return m, notes_added

  def build_part(inst_factory, per_bar_specs):
    part = stream.Part()
    part.append(inst_factory())
    all_notes = []
    for bar_idx in range(12):
      m, notes_in_bar = _drum_bar(
        per_bar_specs[bar_idx], bar_idx,
        attach_metadata=(bar_idx == 0),
      )
      part.append(m)
      all_notes.extend(notes_in_bar)
    return part, all_notes

  if profile == "sparse":
    kick_specs   = [[(BEAT_1, 0.5), (BEAT_3, 0.5)]] * 12
    snare_normal = [[(BEAT_2, 0.5), (BEAT_4, 0.5)]] * 12
    snare_ghost  = [[(BEAT_3 + eighth, eighth)]] * 12
    hh_specs     = [[(BEAT_1, 0.5), (BEAT_3, 0.5)]] * 12
    kick_part,  kick_notes  = build_part(kick,         kick_specs)
    snare_part, snare_notes = build_part(snare,        snare_normal)
    ghost_part, ghost_notes = build_part(snare,        snare_ghost)
    hh_part,    hh_notes    = build_part(closed_hihat, hh_specs)
    anchor_first = kick_notes[:1]
    with_velocity(anchor_first, 65, mark_dynamics=True)
    with_velocity(kick_notes[1:],  65)
    with_velocity(snare_notes,     65)
    with_velocity(hh_notes,        65)
    with_velocity(ghost_notes,     "ghost")
    parts = [kick_part, snare_part, ghost_part, hh_part]
  elif profile == "driving":
    kick_specs        = [[(BEAT_1, 0.5), (BEAT_2, 0.5),
                          (BEAT_3, 0.5), (BEAT_4, 0.5)]] * 12
    snare_backbeat    = [[(BEAT_2, 0.5), (BEAT_4, 0.5)]] * 12
    ride_specs        = [[(BEAT_1, 0.5), (BEAT_2, 0.5),
                          (BEAT_3, 0.5), (BEAT_4, 0.5)]] * 12
    crash_specs       = [[(BEAT_1, 0.5)]] + [[]] * 11
    kick_part,  kick_notes  = build_part(kick,         kick_specs)
    snare_part, snare_notes = build_part(snare,        snare_backbeat)
    ride_part,  ride_notes  = build_part(ride_cymbal,  ride_specs)
    crash_part, crash_notes = build_part(crash_cymbal, crash_specs)
    anchor_first = kick_notes[:1]
    with_velocity(anchor_first, "human", mark_dynamics=True)
    with_velocity(kick_notes[1:], "human")
    with_velocity(snare_notes,    "accent")
    with_velocity(ride_notes,     "human")
    with_velocity(crash_notes,    100)
    parts = [kick_part, snare_part, ride_part, crash_part]
  else:  # 'standard'
    kick_specs    = [[(BEAT_1, 0.5), (BEAT_3, 0.5)]] * 12
    snare_normal  = [[(BEAT_2, 0.5), (BEAT_4, 0.5)]] * 12
    snare_ghost   = [[(BEAT_4 + eighth, eighth)]] * 12
    hh_specs      = [[(BEAT_1, 0.5), (BEAT_2, 0.5),
                      (BEAT_3, 0.5), (BEAT_4, 0.5)]] * 12
    kick_part,  kick_notes  = build_part(kick,         kick_specs)
    snare_part, snare_notes = build_part(snare,        snare_normal)
    ghost_part, ghost_notes = build_part(snare,        snare_ghost)
    hh_part,    hh_notes    = build_part(closed_hihat, hh_specs)
    anchor_first = kick_notes[:1]
    with_velocity(anchor_first, "human", mark_dynamics=True)
    with_velocity(kick_notes[1:], "human")
    with_velocity(snare_notes,    "human")
    with_velocity(hh_notes,       "human")
    with_velocity(ghost_notes,    "ghost")
    parts = [kick_part, snare_part, ghost_part, hh_part]

  return voices(*parts)


def drums_shuffle():
  """A 12-bar shuffle drum pattern in 12/8 — kick on beats 1+3, snare
  on 2+4, hi-hat on every dotted-quarter beat. The rhythmic backbone
  of a slow blues. Returns a Score with three parts (kick, snare,
  hihat). 12 bars in 12/8."""
  ts = meter.TimeSignature("12/8")
  bar_ql = ts.barDuration.quarterLength
  KICK_BEATS  = [0, 6]
  SNARE_BEATS = [3, 9]
  HIHAT_BEATS = [0, 3, 6, 9]

  def make_drum_part(inst, hit_positions):
    part = stream.Part()
    part.append(inst)
    for bar_idx in range(12):
      m = stream.Measure(number=bar_idx + 1)
      if bar_idx == 0:
        m.append(ts)
      cursor = 0.0
      for pos in sorted(hit_positions):
        gap = pos * 0.5 - cursor
        if gap > 0:
          m.append(note.Rest(quarterLength=gap))
          cursor += gap
        hit = note.Note("C4")
        hit.duration = duration.Duration(0.5)
        m.append(hit)
        cursor += 0.5
      remaining = bar_ql - cursor
      if remaining > 0:
        m.append(note.Rest(quarterLength=remaining))
      part.append(m)
    return part

  k_part = make_drum_part(instrument.BassDrum(),    KICK_BEATS)
  s_part = make_drum_part(instrument.SnareDrum(),   SNARE_BEATS)
  h_part = make_drum_part(instrument.HiHatCymbal(), HIHAT_BEATS)
  return voices(k_part, s_part, h_part)


def guitar_solo_chorus():
  """A 12-bar instrumental solo chorus over the song's harmonic frame
  on electric guitar. Twelve bars in 12/8, sitting in the key from
  `form()`. Minor pentatonic with blue notes; chord-tone-aware bar
  pattern picker that breathes with the underlying progression
  (I/IV/V turnaround). Improvisational within each bar."""
  import copy as _copy
  src = form()

  found_key = next((el for el in src.flatten() if isinstance(el, key.Key)), None)
  found_ts = next((el for el in src.flatten() if isinstance(el, meter.TimeSignature)), None)
  found_mm = next((el for el in src.flatten() if isinstance(el, tempo.MetronomeMark)), None)

  tonic_name = found_key.tonic.name if found_key else "E"
  key_mode = found_key.mode if found_key else "minor"
  ts_str = found_ts.ratioString if found_ts else "12/8"
  bpm = found_mm.number if found_mm else 70

  ts = meter.TimeSignature(ts_str)
  bar_ql = ts.barDuration.quarterLength

  if found_ts and found_ts.beatDuration.quarterLength == 1.5:
    mm_referent = duration.Duration(type="quarter", dots=1)
  else:
    mm_referent = duration.Duration("quarter")

  ks = key.Key(tonic_name, key_mode)
  scale_low = minor_pentatonic(ks, octave_range=(4, 5), include_blue=True)
  scale_mid = minor_pentatonic(ks, octave_range=(4, 6), include_blue=True)
  scale_high = minor_pentatonic(ks, octave_range=(5, 6), include_blue=True)

  def chord_tones_for(root_name, quality, octave=4):
    if quality == "minor":
      intervals = [0, 3, 7]
    else:
      intervals = [0, 4, 7]
    root_p = pitch.Pitch(root_name + str(octave))
    return [pitch.Pitch(midi=root_p.midi + i) for i in intervals]

  tonic_root = ks.tonic.name
  iv_root = ks.pitchFromDegree(4).name
  v_root = ks.pitchFromDegree(5).name
  tonic_ct = chord_tones_for(tonic_root, "minor", 4)

  def pick_from(pitches):
    return _random.choice(pitches)

  def make_note(p, ql):
    n = note.Note()
    n.pitch = _copy.deepcopy(p) if hasattr(p, "name") else pitch.Pitch(p)
    n.quarterLength = ql
    return n

  def make_expressive_bar(bar_num, chord_tones, scale, number, density="high"):
    m = stream.Measure(number=number)
    if bar_num == 1:
      m.append(key.Key(tonic_name, key_mode))
      m.append(meter.TimeSignature(ts_str))
      m.append(tempo.MetronomeMark(number=bpm, referent=_copy.deepcopy(mm_referent)))
    dotted_q = 1.5
    if density == "high":
      pattern = [0.5] * 12
    elif density == "medium":
      pattern = [dotted_q, dotted_q, dotted_q, dotted_q]
    else:
      pattern = [2.0, dotted_q, dotted_q, 1.0]
    total = sum(pattern)
    if abs(total - bar_ql) > 0.001:
      pattern = [dotted_q, dotted_q, dotted_q, dotted_q]
    for i, ql in enumerate(pattern):
      if i == 0:
        p = pick_from(chord_tones)
      elif i == len(pattern) - 1:
        p = pick_from(chord_tones)
      else:
        r = _random.random()
        if r < 0.65:
          p = pick_from(scale)
        elif r < 0.85:
          p = pick_from(chord_tones)
        else:
          chromatic_candidates = []
          for ct in chord_tones:
            chromatic_candidates.append(pitch.Pitch(midi=ct.midi + 1))
            chromatic_candidates.append(pitch.Pitch(midi=ct.midi - 1))
          p = pick_from(chromatic_candidates) if chromatic_candidates else pick_from(scale)
      m.append(make_note(p, ql))
    return m

  measures = []
  bars_1_4_patterns = ["medium", "high", "high", "medium"]
  for b in range(4):
    sc = scale_mid if b < 2 else scale_high
    measures.append(make_expressive_bar(b + 1, tonic_ct, sc, b + 1, density=bars_1_4_patterns[b]))

  iv_ct_higher = chord_tones_for(iv_root, "minor", 5)
  iv_scale = minor_pentatonic(ks, octave_range=(5, 6), include_blue=True)
  for b in range(2):
    density = "high" if b == 0 else "medium"
    measures.append(make_expressive_bar(5 + b, iv_ct_higher, iv_scale, 5 + b, density=density))

  for b in range(2):
    density = "medium" if b == 0 else "high"
    measures.append(make_expressive_bar(7 + b, tonic_ct, scale_high, 7 + b, density=density))

  v_ct_mid = chord_tones_for(v_root, "minor", 4)
  measures.append(make_expressive_bar(9, v_ct_mid, scale_high, 9, density="high"))
  iv_ct_mid = chord_tones_for(iv_root, "minor", 4)
  measures.append(make_expressive_bar(10, iv_ct_mid, scale_mid, 10, density="high"))
  measures.append(make_expressive_bar(11, tonic_ct, scale_mid, 11, density="medium"))
  measures.append(make_expressive_bar(12, v_ct_mid, scale_low, 12, density="medium"))

  part = stream.Part()
  part.append(instrument.ElectricGuitar())
  for m in measures:
    part.append(m)
  score = stream.Score()
  score.append(part)
  return score


def vocal_phrase_a():
  """The first vocal phrase of a 12-bar blues lyric (the A line of
  AAB). Four bars in 12/8 in the key from `form()`. A weary
  descending line that leans on the flat-7 and settles on the tonic
  — the setup of the lyric, not the punchline. Sparse, with lots of
  rests, sighing through it."""
  src = form()
  found_key = next((el for el in src.flatten() if isinstance(el, key.Key)), None)
  found_ts = next((el for el in src.flatten() if isinstance(el, meter.TimeSignature)), None)
  found_mm = next((el for el in src.flatten() if isinstance(el, tempo.MetronomeMark)), None)
  tonic_name = found_key.tonic.name if found_key else "E"
  mode_str = found_key.mode if found_key else "minor"
  ts_str = found_ts.ratioString if found_ts else "12/8"
  bpm = found_mm.number if found_mm else 70

  k = found_key if found_key else key.Key(tonic_name, mode_str)
  tonic_p = pitch.Pitch(k.tonic.name + "4")
  fifth_p = pitch.Pitch(k.pitchFromDegree(5).name + "4")
  flat7_p = pitch.Pitch(k.pitchFromDegree(7).name + "4")
  third_p = pitch.Pitch(k.pitchFromDegree(3).name + "4")
  fourth_p = pitch.Pitch(k.pitchFromDegree(4).name + "4")
  flat7_name = flat7_p.nameWithOctave

  ks = key.Key(tonic_name, mode_str)
  ts1 = meter.TimeSignature(ts_str)
  mm = tempo.MetronomeMark(number=bpm, referent=duration.Duration(type="quarter", dots=1))

  m1 = bar(
    note.Rest(quarterLength=1.5),
    note.Note(fifth_p.nameWithOctave, quarterLength=1.5),
    note.Note(fourth_p.nameWithOctave, quarterLength=1.0),
    note.Note(third_p.nameWithOctave, quarterLength=0.5),
    note.Rest(quarterLength=1.5),
    time_signature=ts1, number=1,
  )
  m1.insert(0, mm)
  m1.insert(0, ks)

  m2 = bar(
    note.Rest(quarterLength=1.5),
    note.Note(third_p.nameWithOctave, quarterLength=1.0),
    note.Note(tonic_p.nameWithOctave, quarterLength=0.5),
    note.Note(pitch.Pitch(k.pitchFromDegree(3).name + "4").nameWithOctave, quarterLength=1.5),
    note.Rest(quarterLength=1.5),
    time_signature=ts1, number=2,
  )
  m3 = bar(
    note.Rest(quarterLength=1.5),
    note.Note(flat7_name, quarterLength=2.0),
    note.Note(fourth_p.nameWithOctave, quarterLength=1.0),
    note.Rest(quarterLength=1.5),
    time_signature=ts1, number=3,
  )
  m4 = bar(
    note.Rest(quarterLength=1.5),
    note.Note(third_p.nameWithOctave, quarterLength=1.0),
    note.Note(tonic_p.nameWithOctave, quarterLength=2.0),
    note.Rest(quarterLength=1.5),
    time_signature=ts1, number=4,
  )

  part = stream.Part()
  part.append(instrument.Vocalist())
  part.append(m1); part.append(m2); part.append(m3); part.append(m4)
  score = stream.Score()
  score.append(part)
  return score


def vocal_phrase_b():
  """The B line of the AAB blues lyric — the answer, the punchline,
  the resolution. Four bars in 12/8 in the key from `form()`. Starts
  higher than phrase A (around the octave above tonic), descends
  through pentatonic, touches the blue note, lands on tonic by the
  last bar. More notes, fewer rests than the A line."""
  import copy as _copy
  src = form()
  found_key = next((el for el in src.flatten() if isinstance(el, key.Key)), None)
  found_ts = next((el for el in src.flatten() if isinstance(el, meter.TimeSignature)), None)
  found_mm = next((el for el in src.flatten() if isinstance(el, tempo.MetronomeMark)), None)
  tonic_name = found_key.tonic.name if found_key else "E"
  mode_str = found_key.mode if found_key else "minor"
  ts_str = found_ts.ratioString if found_ts else "12/8"
  bpm = found_mm.number if found_mm else 70

  ts = meter.TimeSignature(ts_str)
  bar_ql = ts.barDuration.quarterLength
  ks = key.Key(tonic_name, mode_str)
  k_scale = minor_pentatonic(ks, octave_range=(4, 6), include_blue=True)
  tonic_midi_4 = pitch.Pitch(tonic_name + "4").midi
  tonic_midi_5 = pitch.Pitch(tonic_name + "5").midi

  def closest_scale_pitch(midi_target):
    return min(k_scale, key=lambda p: abs(p.midi - midi_target))

  entry = closest_scale_pitch(tonic_midi_5 + 3)
  b7 = closest_scale_pitch(tonic_midi_5 - 2)
  fifth = closest_scale_pitch(tonic_midi_5 - 5)
  b5_candidates = [p for p in k_scale if abs(p.midi - (tonic_midi_4 + 6)) <= 1]
  blue = b5_candidates[0] if b5_candidates else closest_scale_pitch(tonic_midi_4 + 6)
  fourth = closest_scale_pitch(tonic_midi_4 + 5)
  minor3 = closest_scale_pitch(tonic_midi_4 + 3)
  tonic4 = closest_scale_pitch(tonic_midi_4)

  def make_note(p, ql):
    n = note.Note()
    n.pitch = _copy.deepcopy(p)
    n.quarterLength = ql
    return n

  part = stream.Part()
  part.append(instrument.Vocalist())

  m1 = stream.Measure(number=1)
  m1.append(_copy.deepcopy(ks))
  m1.append(meter.TimeSignature(ts_str))
  m1.append(tempo.MetronomeMark(number=bpm, referent=duration.Duration(type="quarter", dots=1)))
  n1 = make_note(entry, 3.0)
  n2 = make_note(closest_scale_pitch(entry.midi - 2), 1.5)
  n3 = make_note(closest_scale_pitch(b7.midi), 1.5)
  m1.append(n1); m1.append(n2); m1.append(n3)
  rem1 = bar_ql - (n1.quarterLength + n2.quarterLength + n3.quarterLength)
  if rem1 > 0:
    m1.append(note.Rest(quarterLength=rem1))

  m2 = stream.Measure(number=2)
  m2.append(make_note(_copy.deepcopy(b7), 1.5))
  m2.append(make_note(fifth, 1.5))
  m2.append(make_note(closest_scale_pitch(fifth.midi - 1), 1.5))
  m2.append(make_note(fifth, 1.5))

  m3 = stream.Measure(number=3)
  m3.append(make_note(fourth, 1.5))
  m3.append(make_note(blue, 1.5))
  m3.append(make_note(minor3, 1.5))
  m3.append(make_note(tonic4, 1.5))

  m4 = stream.Measure(number=4)
  m4.append(make_note(tonic4, 3.0))
  m4.append(make_note(closest_scale_pitch(tonic_midi_4 - 1), 1.5))
  m4.append(make_note(tonic4, 1.5))

  part.append(m1); part.append(m2); part.append(m3); part.append(m4)
  score = stream.Score()
  score.append(part)
  return score


def phase_cell():
  """The Reich 'Clapping Music' 12-eighth rhythmic cell as a plain dict
  designed for consumption by `phase_shifter`. Carries: percussion
  instrument factory (closed hi-hat — the FACTORY ref, not an
  instance; the shifter calls it per voice), hit positions in eighth-
  units within the cell (Reich's `[0, 1, 2, 4, 5, 7, 9, 10]` — 8 hits
  across 12 positions), and the cell length in eighths (12)."""
  return {
    "instrument": closed_hihat,
    "hits_in_eighths": [0, 1, 2, 4, 5, 7, 9, 10],
    "length_eighths": 12,
  }


def phase_shifter(*, cell, num_voices=4, bars_per_section=4,
                  total_sections=8, shift_per_section_eighths=1,
                  ts_str="12/8", bpm=96, velocity_profile="human"):
  """A parameterized phase-canon engine. Takes a rhythmic cell (from
  `phase_cell()` or any compatible dict) plus shape parameters and
  returns a Score with N stacked Parts playing the cell repeatedly,
  each voice K (1-indexed) accumulating an integer eighth-note phase
  shift per section. For defaults (4 voices, 1-eighth shift per
  section, 12-eighth cell), voice 4 realigns with voice 1 at section
  4; voice 3 realigns at section 6. Default shape: 12/8 at 96 BPM,
  8 sections × 4 bars/section = 32 bars; eighth-note hits."""
  ts = meter.TimeSignature(ts_str)
  mm = tempo.MetronomeMark(number=bpm)
  eighth_ql = 0.5
  cell_length = cell["length_eighths"]
  hits = list(cell["hits_in_eighths"])
  inst_factory = cell["instrument"]

  def build_bar(rotated_hits, measure_number, first_in_part):
    m = stream.Measure(number=measure_number)
    if first_in_part:
      m.append(ts)
      m.append(mm)
    rotated = sorted(rotated_hits)
    cursor_eighths = 0
    non_rest_notes = []
    for pos in rotated:
      gap = pos - cursor_eighths
      if gap > 0:
        m.append(note.Rest(quarterLength=gap * eighth_ql))
        cursor_eighths += gap
      n = note.Note("C4", quarterLength=eighth_ql)
      m.append(n)
      non_rest_notes.append(n)
      cursor_eighths += 1
    remaining_eighths = cell_length - cursor_eighths
    if remaining_eighths > 0:
      m.append(note.Rest(quarterLength=remaining_eighths * eighth_ql))
    return m, non_rest_notes

  score = stream.Score()
  for k in range(1, num_voices + 1):
    part = stream.Part()
    part.append(inst_factory())
    all_notes_in_part = []
    for s in range(total_sections):
      offset = ((k - 1) * shift_per_section_eighths * s) % cell_length
      rotated_hits = [(h + offset) % cell_length for h in hits]
      for bar_in_section in range(bars_per_section):
        measure_number = s * bars_per_section + bar_in_section + 1
        first_in_part = (measure_number == 1)
        m, notes_in_bar = build_bar(rotated_hits, measure_number, first_in_part)
        part.append(m)
        all_notes_in_part.extend(notes_in_bar)
    if all_notes_in_part:
      with_velocity(all_notes_in_part, velocity_profile)
    score.insert(0, part)
  return score
