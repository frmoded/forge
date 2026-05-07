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

from music21 import instrument, key, meter, note, pitch, stream

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
  in sequence(). Parts with no instrument share an empty-string key."""
  inst = next((el for el in part.elements
               if isinstance(el, instrument.Instrument)), None)
  if inst is None:
    return ''
  return type(inst).__name__


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

  # Per-input bar count and bar_ql, used to pad missing or
  # different-instrument voices. Derived from the first part with measures.
  per_input_padding = []
  for parts in per_input_parts:
    n_bars = 0
    bar_ql = 4.0
    for part in parts:
      measures = list(part.getElementsByClass(stream.Measure))
      if measures:
        n_bars = len(measures)
        first_ts = next(
          (el for m in measures for el in m
           if isinstance(el, meter.TimeSignature)),
          None,
        )
        if first_ts is not None:
          bar_ql = first_ts.barDuration.quarterLength
        break
    per_input_padding.append((n_bars, bar_ql))

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
      key = _instrument_key(src_part)
      if key not in groups:
        groups[key] = []
        order.append(key)
      groups[key].append((input_idx, src_part))

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
          n_bars, bar_ql = per_input_padding[input_idx]
          for _ in range(n_bars):
            m = stream.Measure(number=next_measure_number)
            m.append(note.Rest(quarterLength=bar_ql))
            combined.append(m)
            next_measure_number += 1

      score.insert(0, combined)
  return score


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


def pentatonic(
  key_or_tonic: Union[key.Key, str],
  mode: str = 'minor',
  octave_range: tuple[int, int] = (4, 5),
  include_blue: bool = False,
) -> list[pitch.Pitch]:
  """Return pentatonic scale pitches across the given octave range,
  ordered low-to-high. Mode is 'minor' or 'major'. include_blue=True
  adds the b5."""
  if mode not in _PENTATONIC_INTERVALS:
    raise ValueError(f"mode must be 'minor' or 'major', got {mode!r}")

  if isinstance(key_or_tonic, key.Key):
    tonic_name = key_or_tonic.tonic.name
  else:
    tonic_name = str(key_or_tonic)

  intervals = list(_PENTATONIC_INTERVALS[mode])
  if include_blue:
    intervals.append(6)
    intervals.sort()

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
