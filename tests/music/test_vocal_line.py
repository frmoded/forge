"""Tests for vocal_line — drain 2026-07-10-1340 phase 4.

Verifies the pinned invariants per D-note-4:
- Returns music21.stream.Part with a voice-specific Instrument first;
  falls back to Vocalist if the voice class isn't available in this
  music21 build.
- Voice type enum: soprano (C4-C6) | alto (G3-G5) | tenor (C3-C5) |
  baritone (F2-F4).
- Form=AAB: 12 measures split 4 + 4 + 4. Phrases A and A' share their
  starting pitch (same shape); phrase B ends on the key's tonic.
- Empty `lyrics=` → no Lyric annotations; non-empty → Lyric attached
  to at least the input word count.
- Invalid voice_type / form raises ValueError.
- Non-12-bar harmony raises ValueError.
"""

import pytest
from music21 import instrument, stream

from forge.music.lib import form, vocal_line


def _voice_class(voice_type):
  cls = getattr(instrument, voice_type.capitalize(), None)
  if cls is None:
    cls = getattr(instrument, "Vocalist", None)
  return cls


def _all_notes(part):
  return list(part.recurse().notes)


def test_returns_part_with_voice_instrument():
  """Alto voice: expected `instrument.Alto` in this music21 build.
  Falls back to Vocalist otherwise — assert one of those."""
  h = form()
  vl = vocal_line(h)
  assert isinstance(vl, stream.Part)
  insts = list(vl.getElementsByClass(instrument.Instrument))
  assert insts, "Part must carry an Instrument"
  inst0 = insts[0]
  expected = _voice_class("alto")
  assert isinstance(inst0, expected), (
    f"expected {expected.__name__}; got {type(inst0).__name__}"
  )


def test_alto_pitches_in_g3_g5():
  """Alto register: MIDI 55 (G3) to 79 (G5) inclusive."""
  h = form()
  vl = vocal_line(h, voice_type="alto")
  midis = [n.pitch.midi for n in _all_notes(vl)]
  assert min(midis) >= 55 and max(midis) <= 79, (
    f"alto register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [55, 79]"
  )


def test_soprano_pitches_in_c4_c6():
  h = form()
  vl = vocal_line(h, voice_type="soprano")
  midis = [n.pitch.midi for n in _all_notes(vl)]
  assert min(midis) >= 60 and max(midis) <= 84, (
    f"soprano register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [60, 84]"
  )


def test_tenor_pitches_in_c3_c5():
  h = form()
  vl = vocal_line(h, voice_type="tenor")
  midis = [n.pitch.midi for n in _all_notes(vl)]
  assert min(midis) >= 48 and max(midis) <= 72, (
    f"tenor register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [48, 72]"
  )


def test_baritone_pitches_in_f2_f4():
  h = form()
  vl = vocal_line(h, voice_type="baritone")
  midis = [n.pitch.midi for n in _all_notes(vl)]
  assert min(midis) >= 41 and max(midis) <= 65, (
    f"baritone register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [41, 65]"
  )


def test_form_aab_has_12_measures_split_4_4_4():
  """The AAB form runs 12 bars; each phrase is 4 bars. The measure
  count itself is asserted, plus 4 notes per bar (48 notes total)."""
  h = form()
  vl = vocal_line(h)
  measures = list(vl.getElementsByClass(stream.Measure))
  assert len(measures) == 12, f"expected 12 measures; got {len(measures)}"
  # 4 notes per bar × 12 bars = 48.
  notes = _all_notes(vl)
  assert len(notes) == 48, f"expected 48 notes; got {len(notes)}"


def test_phrase_a_and_a_prime_share_starting_pitch():
  """Phrase A begins at note index 0; Phrase A' at note index 16.
  Both should share the same starting pitch because they're built from
  the same chord (both bars start on the I chord in the blues form)."""
  h = form()
  vl = vocal_line(h)
  notes = _all_notes(vl)
  a_start = notes[0].pitch.nameWithOctave
  a_prime_start = notes[16].pitch.nameWithOctave
  assert a_start == a_prime_start, (
    f"phrase A start {a_start!r} should match phrase A' start "
    f"{a_prime_start!r}"
  )


def test_phrase_b_ends_on_tonic():
  """The final note of phrase B (measure 12, note 48) must have the
  same pitch class as the harmony's key tonic (E for E major default
  form)."""
  h = form()
  vl = vocal_line(h)
  notes = _all_notes(vl)
  final_pc = notes[-1].pitch.name
  # form() defaults to E major.
  assert final_pc == "E", (
    f"phrase B final note should be tonic (E); got {final_pc!r}"
  )


def test_empty_lyrics_leaves_no_lyric_annotations():
  h = form()
  vl = vocal_line(h, lyrics="")
  with_lyrics = [n for n in _all_notes(vl) if n.lyric is not None]
  assert not with_lyrics, (
    f"empty lyrics: expected no Lyric annotations; got "
    f"{len(with_lyrics)}"
  )


def test_lyrics_attach_words_to_notes():
  """Non-empty lyrics: each word gets attached to some note. With
  fewer words than notes, the number of annotated notes equals the
  number of words."""
  h = form()
  words = "woke up feeling blue"  # 4 words
  vl = vocal_line(h, lyrics=words)
  n_with_lyric = sum(1 for n in _all_notes(vl) if n.lyric is not None)
  n_words = len(words.split())
  assert n_with_lyric == n_words, (
    f"expected {n_words} notes with lyric; got {n_with_lyric}"
  )


def test_invalid_voice_type_raises():
  h = form()
  with pytest.raises(ValueError, match="voice_type"):
    vocal_line(h, voice_type="mezzo")


def test_invalid_form_raises():
  h = form()
  with pytest.raises(ValueError, match="form"):
    vocal_line(h, form="ABA")


def test_invalid_style_raises():
  h = form()
  with pytest.raises(ValueError, match="style"):
    vocal_line(h, style="soul")


def test_non_12_bar_harmony_raises():
  """AAB form requires exactly 12 measures — a shorter progression
  raises ValueError."""
  short_prog = ["I", "IV", "V"]  # 3 measures only
  h = form(progression=short_prog)
  with pytest.raises(ValueError, match="12 measures"):
    vocal_line(h)
