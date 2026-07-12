"""Tests for piano_voicing — drain 2026-07-10-1340 phase 2.

Verifies the pinned invariants per D-note-1:
- Returns music21.stream.Part with a Piano instrument first.
- Style enum: rootless | stride | block; voicing sizes 4 / 5 / 4.
- Register enum: low (C2-C4) | mid (C3-C5) | high (C4-C6). Every
  pitch in every voicing must fall within the range.
- Rhythm enum: charleston | straight_quarters | eighth_comping.
- Invalid style / register / rhythm raise ValueError.
"""

import pytest
from music21 import chord, instrument, stream

from forge.music.lib import form, piano_voicing


def _all_chords(part):
  return [c for m in part.getElementsByClass(stream.Measure)
          for c in m.getElementsByClass(chord.Chord)]


def _all_pitch_midis(part):
  midis = []
  for c in _all_chords(part):
    midis.extend(p.midi for p in c.pitches)
  return midis


def test_returns_part_with_piano():
  h = form()
  pv = piano_voicing(h)
  assert isinstance(pv, stream.Part)
  insts = list(pv.getElementsByClass(instrument.Instrument))
  assert insts, "Part must carry an Instrument as its first element"
  assert isinstance(insts[0], instrument.Piano), (
    f"expected Piano; got {type(insts[0]).__name__}"
  )


def test_straight_quarters_has_four_hits_per_bar():
  h = form()
  pv = piano_voicing(h, rhythm="straight_quarters")
  for m in pv.getElementsByClass(stream.Measure):
    chords = list(m.getElementsByClass(chord.Chord))
    assert len(chords) == 4, (
      f"straight_quarters bar {m.number}: expected 4 chord hits, "
      f"got {len(chords)}"
    )


def test_charleston_has_two_hits_per_bar_in_12_8():
  """Default `form()` is 12/8. Charleston fires on beats 1 and 3 —
  two dotted-quarter chord hits per bar."""
  h = form()  # 12/8
  pv = piano_voicing(h, rhythm="charleston")
  for m in pv.getElementsByClass(stream.Measure):
    chords = list(m.getElementsByClass(chord.Chord))
    assert len(chords) == 2, (
      f"charleston (12/8) bar {m.number}: expected 2 hits, "
      f"got {len(chords)}"
    )


def test_eighth_comping_has_twelve_hits_per_bar_in_12_8():
  h = form()  # 12/8 → 12 hits.
  pv = piano_voicing(h, rhythm="eighth_comping")
  for m in pv.getElementsByClass(stream.Measure):
    chords = list(m.getElementsByClass(chord.Chord))
    assert len(chords) == 12, (
      f"eighth_comping (12/8) bar {m.number}: expected 12 hits, "
      f"got {len(chords)}"
    )


def test_rootless_voicing_has_four_pitches():
  h = form()
  pv = piano_voicing(h, style="rootless")
  for c in _all_chords(pv):
    assert len(c.pitches) == 4, (
      f"rootless voicing must have 4 pitches; got {len(c.pitches)}"
    )


def test_stride_voicing_has_five_pitches():
  h = form()
  pv = piano_voicing(h, style="stride")
  for c in _all_chords(pv):
    assert len(c.pitches) == 5, (
      f"stride voicing must have 5 pitches; got {len(c.pitches)}"
    )


def test_block_voicing_has_four_pitches():
  h = form()
  pv = piano_voicing(h, style="block")
  for c in _all_chords(pv):
    assert len(c.pitches) == 4, (
      f"block voicing must have 4 pitches; got {len(c.pitches)}"
    )


def test_low_register_pitches_in_c2_to_c4():
  """Low register bounds: MIDI 36 (C2) to 60 (C4) inclusive."""
  h = form()
  pv = piano_voicing(h, register="low", style="rootless")
  midis = _all_pitch_midis(pv)
  assert midis, "expected some pitches"
  assert min(midis) >= 36, (
    f"low register: found pitch below C2 (midi {min(midis)})"
  )
  assert max(midis) <= 60, (
    f"low register: found pitch above C4 (midi {max(midis)})"
  )


def test_mid_register_pitches_in_c3_to_c5():
  """Mid register: MIDI 48 (C3) to 72 (C5) inclusive."""
  h = form()
  pv = piano_voicing(h, register="mid", style="rootless")
  midis = _all_pitch_midis(pv)
  assert min(midis) >= 48 and max(midis) <= 72, (
    f"mid register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [48, 72]"
  )


def test_high_register_pitches_in_c4_to_c6():
  """High register: MIDI 60 (C4) to 84 (C6) inclusive."""
  h = form()
  pv = piano_voicing(h, register="high", style="rootless")
  midis = _all_pitch_midis(pv)
  assert min(midis) >= 60 and max(midis) <= 84, (
    f"high register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [60, 84]"
  )


def test_invalid_style_raises():
  h = form()
  with pytest.raises(ValueError, match="style"):
    piano_voicing(h, style="modal")


def test_invalid_register_raises():
  h = form()
  with pytest.raises(ValueError, match="register"):
    piano_voicing(h, register="stratosphere")


def test_invalid_rhythm_raises():
  h = form()
  with pytest.raises(ValueError, match="rhythm"):
    piano_voicing(h, rhythm="tresillo")


def test_charleston_in_4_4_uses_dotted_quarter_eighth_half():
  """In 4/4 the charleston figure is dotted-quarter, eighth, half —
  three chord hits per bar covering ql = 4.0 exactly (1.5+0.5+2.0)."""
  h = form(ts_str="4/4")
  pv = piano_voicing(h, rhythm="charleston")
  for m in pv.getElementsByClass(stream.Measure):
    chords = list(m.getElementsByClass(chord.Chord))
    assert len(chords) == 3, (
      f"charleston (4/4) bar {m.number}: expected 3 chord hits; "
      f"got {len(chords)}"
    )
