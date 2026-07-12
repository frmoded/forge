"""Tests for walking_bass_line — drain 2026-07-10-1400 phase 1.

Verifies the pinned test invariants:
- Returns music21.stream.Part.
- Part.instrument is Contrabass (double_bass) or ElectricBass (electric_bass).
- Number of notes = 4 × number of measures in harmony.
- Roots on beat 1; fifths on beat 3.

Notes: pitches are transposed into bass register (octave 2-3). The
"swing feel: 2:1 quarter-note ratio" invariant from the drain prompt
does NOT apply to quarter-note walking in 4/4 or dotted-quarter walking
in 12/8 (in 12/8 the swing feel is inherent to the compound meter); the
`style` param is accepted for API stability without altering rhythm.
That divergence is called out in the drain 1400 FEEDBACK.
"""

import pytest
from music21 import instrument, meter, note, stream

from forge.music.lib import form, walking_bass_line


def _flat_notes(part):
  return list(part.recurse().notes)


def test_returns_stream_part():
  h = form()  # E major, 12/8, standard 12-bar progression
  bl = walking_bass_line(h)
  assert isinstance(bl, stream.Part)


def test_double_bass_uses_contrabass_instrument():
  h = form()
  bl = walking_bass_line(h, instrument_name="double_bass")
  insts = list(bl.getElementsByClass(instrument.Instrument))
  assert insts, "Part should carry an instrument as its first element"
  assert isinstance(insts[0], instrument.Contrabass), (
    f"double_bass must produce Contrabass; got {type(insts[0]).__name__}"
  )


def test_electric_bass_uses_electric_bass_instrument():
  h = form()
  bl = walking_bass_line(h, instrument_name="electric_bass")
  insts = list(bl.getElementsByClass(instrument.Instrument))
  assert insts and isinstance(insts[0], instrument.ElectricBass), (
    f"electric_bass must produce ElectricBass; got "
    f"{type(insts[0]).__name__ if insts else 'none'}"
  )


def test_four_notes_per_measure():
  """Pinned invariant: number of notes = 4 × number of measures."""
  h = form()  # 12-bar progression
  measures = list(list(h.getElementsByClass(stream.Part))[0]
                  .getElementsByClass(stream.Measure))
  bl = walking_bass_line(h)
  notes_out = _flat_notes(bl)
  assert len(notes_out) == 4 * len(measures), (
    f"walking bass should emit 4 notes per bar; got {len(notes_out)} "
    f"notes over {len(measures)} measures"
  )
  # And each output measure should also have exactly 4 notes.
  for i, m in enumerate(bl.getElementsByClass(stream.Measure)):
    m_notes = list(m.notes)
    assert len(m_notes) == 4, (
      f"measure {i+1} has {len(m_notes)} notes, expected 4"
    )


def test_root_on_beat_1_matches_chord_root():
  """Pinned invariant: root on beat 1 of each bar."""
  from music21 import chord as _chord
  h = form()
  source_part = list(h.getElementsByClass(stream.Part))[0]
  measures_in = list(source_part.getElementsByClass(stream.Measure))
  bl = walking_bass_line(h)
  measures_out = list(bl.getElementsByClass(stream.Measure))

  for i, (m_in, m_out) in enumerate(zip(measures_in, measures_out)):
    chords = m_in.getElementsByClass(_chord.Chord)
    if not chords:
      pytest.skip(f"measure {i+1} of harmony has no Chord; skipping")
    expected_root_name = chords[0].root().name
    beat_1 = list(m_out.notes)[0]
    assert beat_1.pitch.name == expected_root_name, (
      f"measure {i+1}: beat 1 should be chord root {expected_root_name}; "
      f"got {beat_1.pitch.name}"
    )


def test_fifth_on_beat_3_matches_chord_fifth():
  """Pinned invariant: fifth on beat 3 of each bar. Read as pitch #2
  (index 2) of the chord's pitches in root position."""
  from music21 import chord as _chord
  h = form()
  source_part = list(h.getElementsByClass(stream.Part))[0]
  measures_in = list(source_part.getElementsByClass(stream.Measure))
  bl = walking_bass_line(h)
  measures_out = list(bl.getElementsByClass(stream.Measure))

  for i, (m_in, m_out) in enumerate(zip(measures_in, measures_out)):
    chords = m_in.getElementsByClass(_chord.Chord)
    if not chords or len(chords[0].pitches) < 3:
      pytest.skip(
        f"measure {i+1} of harmony lacks a fifth in its chord; skipping"
      )
    expected_fifth_name = chords[0].pitches[2].name
    beat_3 = list(m_out.notes)[2]
    assert beat_3.pitch.name == expected_fifth_name, (
      f"measure {i+1}: beat 3 should be chord fifth "
      f"{expected_fifth_name}; got {beat_3.pitch.name}"
    )


def test_notes_are_in_bass_register():
  """All notes should fall in octave 2-3 (bass clef range)."""
  h = form()
  bl = walking_bass_line(h)
  for n in _flat_notes(bl):
    assert 2 <= n.pitch.octave <= 3, (
      f"note {n.pitch.nameWithOctave} out of bass register (octave 2-3)"
    )


def test_note_duration_matches_time_signature():
  """In 12/8 (bar_ql=6): 4 dotted-quarter notes at ql=1.5. In 4/4
  (bar_ql=4): 4 quarter notes at ql=1.0."""
  h_12_8 = form()  # default 12/8
  bl_12_8 = walking_bass_line(h_12_8)
  for n in _flat_notes(bl_12_8):
    assert n.duration.quarterLength == 1.5, (
      f"12/8 walking bass should use dotted-quarter (ql=1.5); "
      f"got ql={n.duration.quarterLength}"
    )

  h_4_4 = form(ts_str="4/4")
  bl_4_4 = walking_bass_line(h_4_4)
  for n in _flat_notes(bl_4_4):
    assert n.duration.quarterLength == 1.0, (
      f"4/4 walking bass should use quarter (ql=1.0); "
      f"got ql={n.duration.quarterLength}"
    )


def test_invalid_instrument_raises():
  h = form()
  with pytest.raises(ValueError, match="instrument_name"):
    walking_bass_line(h, instrument_name="tuba")


def test_invalid_style_raises():
  h = form()
  with pytest.raises(ValueError, match="style"):
    walking_bass_line(h, style="latin")


def test_composes_into_voices_list():
  """Integration: walking_bass_line output is a valid Part suitable for
  voices_list composition alongside `form`. Confirms the compose-from-
  atoms pattern the drain aims for."""
  from forge.music.lib import voices_list
  h = form()
  bl = walking_bass_line(h)
  score = voices_list([h, bl])
  assert isinstance(score, stream.Score)
  # The score should carry both parts.
  parts = list(score.getElementsByClass(stream.Part))
  # voices_list may flatten/nest; just assert we didn't lose the bass
  # notes.
  all_notes = list(score.recurse().notes)
  # 12 measures × 4 notes = 48 bass notes minimum (plus harmony's own
  # chord tones)
  bass_notes = [n for n in all_notes
                if hasattr(n, 'pitch') and n.pitch.octave <= 3]
  assert len(bass_notes) >= 48, (
    f"composition should preserve all 48 bass notes; got {len(bass_notes)}"
  )
