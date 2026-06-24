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

from music21 import clef, instrument, key, meter, note, pitch, stream

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

# Map (m21_class_name, percMapPitch_or_None) → (kit_pitch, voice, notehead).
# When percMapPitch is None in the key, that's the catch-all for the class.
_KIT_NOTATION_MAP = {
  # Kick — voice 2 stems down.
  ('BassDrum', None): ('B1', _KIT_VOICE_FEET, 'normal'),
  # Snare — voice 1, middle line.
  ('SnareDrum', None): ('E2', _KIT_VOICE_HANDS, 'normal'),
  # Hi-hats — closed/open/pedal share HiHatCymbal class, differ on
  # percMapPitch (42 / 46 / 44 per the lib.py factories).
  ('HiHatCymbal', 42): ('G2', _KIT_VOICE_HANDS, 'x'),       # closed
  ('HiHatCymbal', 46): ('G2', _KIT_VOICE_HANDS, 'circle-x'),  # open
  ('HiHatCymbal', 44): ('D2', _KIT_VOICE_FEET, 'x'),         # pedal
  # Catch-all hi-hat (unknown percMapPitch) → treat as closed.
  ('HiHatCymbal', None): ('G2', _KIT_VOICE_HANDS, 'x'),
  # Toms — three variants differ only on percMapPitch (41/47/50).
  ('TomTom', 41): ('F2', _KIT_VOICE_HANDS, 'normal'),  # low
  ('TomTom', 47): ('A2', _KIT_VOICE_HANDS, 'normal'),  # mid
  ('TomTom', 50): ('C3', _KIT_VOICE_HANDS, 'normal'),  # high
  ('TomTom', None): ('A2', _KIT_VOICE_HANDS, 'normal'),  # fallback
  # Cymbals — crash + ride get X-noteheads above staff. music21 class
  # names: CrashCymbals (note the plural), RideCymbals.
  ('CrashCymbals', None): ('A2', _KIT_VOICE_HANDS, 'x'),
  ('RideCymbals', None): ('F3', _KIT_VOICE_HANDS, 'x'),
}


def _kit_lookup(inst):
  """Return (kit_pitch, voice, notehead) for a percussion instrument, or
  None if the instrument isn't a recognized percussion class. Falls back
  through (class_name, percMapPitch) → (class_name, None) so an
  unrecognized percMapPitch within a known class still gets a sane
  default."""
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

  voice_hands = stream.Voice()
  voice_hands.id = '1'
  voice_feet = stream.Voice()
  voice_feet.id = '2'

  # Walk each percussion Part's notes; for each, look up kit position +
  # voice + notehead; insert into the appropriate voice at the same
  # offset.
  for src_part in percussion_parts:
    src_inst = src_part.getInstrument(returnDefault=False)
    src_spec = _kit_lookup(src_inst)
    if src_spec is None:
      # Unknown percussion class; default to hands voice with normal
      # notehead at staff middle line.
      src_spec = ('E2', _KIT_VOICE_HANDS, 'normal')
    kit_pitch, voice_id, notehead_type = src_spec
    # Flatten so we walk Measures, Voices, etc. uniformly.
    for src_note in src_part.recurse().notes:
      # Preserve the original ID + instrument reference. music21 Notes
      # carry editorial dicts; stash the source instrument so MIDI
      # export (which reads instrument context per note) still sees the
      # right percussion channel routing.
      new_note = note.Note(kit_pitch)
      new_note.quarterLength = src_note.quarterLength
      if src_note.id is not None:
        new_note.id = src_note.id
      # Preserve source instrument reference for MIDI walk.
      new_note.editorial.misc['forge_source_instrument'] = src_inst
      # Stems + noteheads per kit conventions.
      if voice_id == _KIT_VOICE_HANDS:
        new_note.stemDirection = 'up'
      else:
        new_note.stemDirection = 'down'
      if notehead_type != 'normal':
        new_note.notehead = notehead_type
      # Preserve velocity / dynamics if present.
      if src_note.volume is not None:
        new_note.volume = copy.deepcopy(src_note.volume)
      # Same offset within the part.
      offset = src_note.getOffsetInHierarchy(src_part)
      if voice_id == _KIT_VOICE_HANDS:
        voice_hands.insert(offset, new_note)
      else:
        voice_feet.insert(offset, new_note)

  # Voice 1 before voice 2 so engraving conventions are respected.
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
