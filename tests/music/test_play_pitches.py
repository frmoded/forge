"""play_pitches — hear a widget's pitch selection back.

CW-forge-music-lib-add-play-pitches-primitive (drain 2026-08-05-2330).
Written FAILING-FIRST: the primitive does not exist yet.

Step-1 divergence pinned here: the prompt's fix shape (write an MP3 +
return a wikilink, "reuse the engine path forge_render_music uses") is
unimplementable where the fixture runs. forge_render_music's mp3
format is a MIDI -> fluidsynth -> ffmpeg pipeline ON THE
FORGE-TRANSPILE HOST (per its own docstring, drain 2026-07-29-1600);
those binaries do not exist inside Pyodide, which is where a Run-click
executes this primitive. The shipped shape instead returns a
music21 Stream — the same hear-it contract every Tier-1 primitive
(rhythmic_line / melodic_line / chord_stream) uses, rendered by the
Forge panel's midi-player. play_pitches delegates to
melodic_line with a uniform quarter-note pattern and accepts the
widget's JSON-string serialization via _coerce_student_pitches.
"""
import pytest

from forge.music import lib


def _notes_of(s):
  from music21 import note as m21note
  return [el for el in s.recurse().notes if isinstance(el, m21note.Note)]


def _tempo_marks(s):
  from music21 import tempo as m21tempo
  return [el for el in s.recurse() if isinstance(el, m21tempo.MetronomeMark)]


def test_play_pitches_returns_stream_of_quarter_notes():
  s = lib.play_pitches(["C4", "E4", "G4"])
  notes = _notes_of(s)
  assert [n.nameWithOctave for n in notes] == ["C4", "E4", "G4"]
  assert all(n.duration.quarterLength == 1.0 for n in notes)


def test_play_pitches_default_tempo_100():
  s = lib.play_pitches(["C4"])
  marks = _tempo_marks(s)
  assert marks and marks[0].number == 100


def test_play_pitches_tempo_override():
  s = lib.play_pitches(["C4", "D4"], tempo=140)
  assert _tempo_marks(s)[0].number == 140


def test_play_pitches_accepts_json_string():
  # The piano / guitar_fretboard widgets serialize the selection as a
  # JSON list string (drain 2026-08-05-1500 contract).
  s = lib.play_pitches('["C4", "E4", "G4"]')
  assert [n.nameWithOctave for n in _notes_of(s)] == ["C4", "E4", "G4"]


def test_play_pitches_empty_returns_no_notes_string():
  assert lib.play_pitches([]) == "(No notes to play)"
  assert lib.play_pitches("[]") == "(No notes to play)"
  assert lib.play_pitches("") == "(No notes to play)"


def test_play_pitches_registration_both_lists():
  # Drain 1730 lesson: a primitive missing from either executor list is
  # invisible to one of the two dispatch paths.
  from forge.core import executor
  if executor._FORGE_MUSIC_LIB_NAMES:
    assert "play_pitches" in executor._FORGE_MUSIC_LIB_NAMES
  assert "play_pitches" in executor._MUSIC_LAZY_CHIP_NAMES
