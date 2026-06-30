"""Smoke tests for the 8 library notes promoted from forge-music vault
engineer-mode files in v0.7.0 (drain 2026-07-01-1800).

Each test asserts the function imports + runs with default kwargs and
returns a non-empty result of the expected shape. These were
context.compute-shaped before; lifting them into the library means the
engine can no longer route via the snippet registry — they must work
as plain Python callables.
"""
import pytest

music21 = pytest.importorskip("music21")
from music21 import stream

from forge.music import lib


def test_form_returns_score_with_12_measures_in_part():
  score = lib.form()
  assert isinstance(score, stream.Score)
  parts = score.parts
  assert len(parts) == 1
  measures = parts[0].getElementsByClass(stream.Measure)
  assert len(measures) == 12


def test_form_respects_progression_override():
  alt_progression = ["I", "V", "I", "V", "I", "V", "I", "V"]
  score = lib.form(progression=alt_progression)
  measures = score.parts[0].getElementsByClass(stream.Measure)
  assert len(measures) == 8


@pytest.mark.parametrize("profile", ["sparse", "standard", "driving"])
def test_drum_chorus_each_profile_returns_score(profile):
  score = lib.drum_chorus(profile=profile)
  assert isinstance(score, stream.Score)
  assert len(score.parts) >= 3  # at least kick / snare / hh


def test_drum_chorus_unknown_profile_falls_back_to_standard():
  # Per existing semantics: anything not 'sparse' or 'driving' picks
  # the standard branch. Don't regress that tolerance.
  score = lib.drum_chorus(profile="bogus")
  assert isinstance(score, stream.Score)


def test_drums_shuffle_returns_score():
  score = lib.drums_shuffle()
  assert isinstance(score, stream.Score)


def test_guitar_solo_chorus_returns_score():
  score = lib.guitar_solo_chorus()
  assert isinstance(score, stream.Score)
  # Solo is on a single electric guitar part.
  assert len(score.parts) == 1


def test_vocal_phrase_a_returns_score():
  score = lib.vocal_phrase_a()
  assert isinstance(score, stream.Score)
  measures = score.parts[0].getElementsByClass(stream.Measure)
  assert len(measures) == 4


def test_vocal_phrase_b_returns_score():
  score = lib.vocal_phrase_b()
  assert isinstance(score, stream.Score)
  measures = score.parts[0].getElementsByClass(stream.Measure)
  assert len(measures) == 4


def test_phase_cell_returns_dict_with_factory():
  cell = lib.phase_cell()
  assert isinstance(cell, dict)
  assert callable(cell["instrument"])
  assert cell["length_eighths"] == 12
  assert cell["hits_in_eighths"] == [0, 1, 2, 4, 5, 7, 9, 10]


def test_phase_shifter_default_returns_score():
  cell = lib.phase_cell()
  score = lib.phase_shifter(cell=cell)
  assert isinstance(score, stream.Score)
  # Default num_voices=4
  assert len(score.parts) == 4


def test_phase_shifter_custom_voice_count():
  cell = lib.phase_cell()
  score = lib.phase_shifter(cell=cell, num_voices=2, total_sections=2)
  assert len(score.parts) == 2


def test_promoted_functions_are_in_domain_globals():
  """Every promoted library note must surface via the music-domain
  globals so vault Recipes calling them (via wikilink → direct call
  in transpiled Python) resolve at exec time."""
  from forge.core import executor
  globals_dict = executor._domain_globals_for(["music"])
  for name in (
    "form", "drum_chorus", "drums_shuffle", "guitar_solo_chorus",
    "vocal_phrase_a", "vocal_phrase_b", "phase_cell", "phase_shifter",
  ):
    assert name in globals_dict, f"{name} missing from music domain globals"
    assert callable(globals_dict[name])
