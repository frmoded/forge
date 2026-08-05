"""chord_stream — third Tier-1 composition primitive.

CW-forge-music-lib-add-chord-stream-tier-1 (drain 2026-08-05-1800).
Written FAILING-FIRST: the primitive does not exist yet.

Step-1 note pinned here: the drain prompt's premise ("should coexist
with chord_progression / major_triad / chord_inversions") is wrong —
none of those exist in the engine lib. chord_stream is genuinely new;
its nearest neighbor, piano_voicing, is a stylized comping generator,
not a plain chord renderer.
"""
import pytest

from forge.music import lib


def _chords_of(s):
  from music21 import chord as m21chord
  return [el for el in s.recurse().notes if isinstance(el, m21chord.Chord)]


def _tempo_marks(s):
  from music21 import tempo as m21tempo
  return [el for el in s.recurse() if isinstance(el, m21tempo.MetronomeMark)]


I_IV_V_I = [
  ["C4", "E4", "G4"],
  ["F4", "A4", "C5"],
  ["G4", "B4", "D5"],
  ["C4", "E4", "G4"],
]


def test_chord_stream_uniform_durations_default():
  s = lib.chord_stream(I_IV_V_I[:3])
  got = _chords_of(s)
  assert len(got) == 3
  assert all(c.quarterLength == 4.0 for c in got)
  # Sequential timing: each chord starts where the prior one ended.
  assert [c.offset for c in got] == [0.0, 4.0, 8.0]


def test_chord_stream_custom_durations():
  s = lib.chord_stream(I_IV_V_I[:3], durations=[1.0, 2.0, 4.0])
  got = _chords_of(s)
  assert [c.quarterLength for c in got] == [1.0, 2.0, 4.0]
  assert [c.offset for c in got] == [0.0, 1.0, 3.0]


def test_chord_stream_accepts_pitch_lists():
  s = lib.chord_stream([["C4", "E4", "G4"], ["G4", "B4", "D5"]])
  got = _chords_of(s)
  assert [p.nameWithOctave for p in got[0].pitches] == ["C4", "E4", "G4"]
  assert [p.nameWithOctave for p in got[1].pitches] == ["G4", "B4", "D5"]


def test_chord_stream_accepts_music21_chords():
  from music21 import chord as m21chord
  pre = [m21chord.Chord(["C4", "E4", "G4"]), m21chord.Chord(["F4", "A4", "C5"])]
  s = lib.chord_stream(pre)
  got = _chords_of(s)
  assert len(got) == 2
  assert got[0].quarterLength == 4.0
  # The caller's objects are not mutated (defensive copy).
  assert pre[0].quarterLength == 1.0


def test_chord_stream_accepts_chord_symbols():
  s = lib.chord_stream(["Cmaj7"])
  got = _chords_of(s)
  assert len(got) == 1
  assert {p.name for p in got[0].pitches} == {"C", "E", "G", "B"}


def test_chord_stream_accepts_midi_number_lists():
  s = lib.chord_stream([[60, 64, 67]])
  got = _chords_of(s)
  assert [p.nameWithOctave for p in got[0].pitches] == ["C4", "E4", "G4"]


def test_chord_stream_mixed_input_types():
  s = lib.chord_stream([["C4", "E4", "G4"], "G7"])
  got = _chords_of(s)
  assert len(got) == 2
  assert {p.name for p in got[1].pitches} == {"G", "B", "D", "F"}


def test_chord_stream_tempo_mark_at_offset_0():
  # Same contract as rhythmic_line + melodic_line.
  s = lib.chord_stream(I_IV_V_I, tempo=90)
  marks = _tempo_marks(s)
  assert len(marks) == 1
  assert marks[0].number == 90
  assert marks[0].offset == 0.0


def test_chord_stream_rejects_empty():
  with pytest.raises(ValueError, match="empty"):
    lib.chord_stream([])


def test_chord_stream_rejects_duration_mismatch():
  with pytest.raises(ValueError, match="durations"):
    lib.chord_stream(I_IV_V_I[:3], durations=[1.0, 2.0])


def test_chord_stream_rejects_nonpositive_duration():
  with pytest.raises(ValueError, match="positive"):
    lib.chord_stream(I_IV_V_I[:2], durations=[4.0, 0.0])


def test_chord_stream_rejects_bad_symbol():
  # Position info per the prompt: the error names WHICH chord is bad.
  with pytest.raises(ValueError, match=r"chords\[2\]"):
    lib.chord_stream([["C4", "E4", "G4"], "G7", "Xq99"])


def test_chord_stream_rejects_bad_pitch_in_list():
  with pytest.raises(ValueError, match=r"chords\[1\]"):
    lib.chord_stream([["C4", "E4", "G4"], ["C4", "notapitch"]])


def test_chord_stream_rejects_bad_tempo():
  with pytest.raises(ValueError, match="tempo"):
    lib.chord_stream(I_IV_V_I, tempo=0)
  with pytest.raises(ValueError, match="tempo"):
    lib.chord_stream(I_IV_V_I, tempo=-60)


def test_chord_stream_registration_lazy_list():
  from forge.core import executor
  assert "chord_stream" in executor._FORGE_MUSIC_LIB_NAMES
  assert "chord_stream" in executor._MUSIC_LAZY_CHIP_NAMES
