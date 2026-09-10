"""Tests for `forge.music.lib.build_triad_chord`.

CW 1245 — sibling to `build_chord` (drain 1210). Same tonic + quality
-> interval-stack -> transpose -> nameWithOctave shape, different
quality vocabulary (triads, not sevenths/extended-dominants).

Named `build_triad_chord`, not `build_triad` — the vault note that
calls this (`build_triad.md`) has that exact basename, and a same-
named chip would shadow itself per `test_library_shadow_guard.py`
(caught live while writing this drain — first attempt used
`build_triad` and failed that guard).

Pitch spellings below are the actual music21 output for `tonic="C4"`,
computed directly rather than hand-guessed (music21's flat convention
is `-`, not `b`).
"""
import re

import pytest

from forge.music import lib

music21 = pytest.importorskip("music21")


class TestBuildTriadChord:
  def test_major(self):
    assert lib.build_triad_chord("C4", "major") == ["C4", "E4", "G4"]

  def test_minor(self):
    assert lib.build_triad_chord("C4", "minor") == ["C4", "E-4", "G4"]

  def test_diminished(self):
    assert lib.build_triad_chord("C4", "diminished") == \
      ["C4", "E-4", "G-4"]

  def test_augmented(self):
    assert lib.build_triad_chord("C4", "augmented") == ["C4", "E4", "G#4"]

  def test_different_tonic(self):
    assert lib.build_triad_chord("D4", "major") == ["D4", "F#4", "A4"]

  def test_unknown_quality_raises_keyerror(self):
    with pytest.raises(KeyError):
      lib.build_triad_chord("C4", "not-a-quality")


def test_registered_in_both_executor_chip_lists():
  """Same registration convention drain 1210 found for build_chord:
  chip must be in BOTH _FORGE_MUSIC_LIB_NAMES and _MUSIC_LAZY_CHIP_NAMES
  or the import-time drift guard raises."""
  from forge.core import executor
  assert executor._FORGE_MUSIC_LIB_NAMES["build_triad_chord"].__qualname__ \
    == "build_triad_chord"
  assert "build_triad_chord" in executor._MUSIC_LAZY_CHIP_NAMES


def test_build_chord_behavior_unchanged_by_the_shared_helper_refactor():
  """If build_triad_chord's implementation factors a helper build_chord
  also uses, build_chord's own public behavior must not move a single
  bit."""
  assert lib.build_chord("C4", "dom7") == ["C4", "E4", "G4", "B-4"]
  assert lib.build_chord("C4", "maj7") == ["C4", "E4", "G4", "B4"]


class TestBuildTriadNoteRegression:
  """End-to-end: the actual `build_triad.md` note, real parse + transpile
  + exec — per the standing "works/verified claims must be tested
  through the real production entry point" rule.
  """

  NOTE_PATH = (
    "/Users/odedfuhrmann/projects/music-theory/theory_exercises/"
    "build_triad.md"
  )

  def _recipe_and_python(self):
    text = open(self.NOTE_PATH, encoding="utf-8").read()
    recipe = re.search(
      r"^# Recipe\s*\n\n(.*?)(?:\n\n# Python|\Z)", text, re.S | re.M
    ).group(1)
    python_match = re.search(
      r"^# Python\s*\n\n```python\n(.*?)\n```", text, re.S | re.M)
    python_block = python_match.group(1) if python_match else None
    return recipe, python_block

  def test_recipe_calls_build_triad_chord_not_build_triad(self):
    """Pins the shape that keeps this note out of the shadow-guard's
    failure mode — regression against the exact bug caught while
    writing this drain."""
    recipe, _ = self._recipe_and_python()
    assert "[[build_triad_chord]]" in recipe
    assert "[[build_triad]]" not in recipe

  def test_recipe_has_no_slot_markers(self):
    recipe, _ = self._recipe_and_python()
    assert "{{" not in recipe and "}}" not in recipe

  def test_stored_python_is_byte_exact_fresh_transpile(self):
    from forge.recipe.parser import parse
    from forge.recipe.transpiler import transpile
    recipe, python_block = self._recipe_and_python()
    assert python_block is not None, "note has no # Python heading"
    transpiled = transpile(parse(recipe), resolve_slot=None)
    assert transpiled.strip() == python_block.strip()

  @pytest.mark.parametrize("tonic,quality,expected", [
    ("C4", "major", ["C4", "E4", "G4"]),
    ("C4", "diminished", ["C4", "E-4", "G-4"]),
  ])
  def test_note_executes_correctly_end_to_end(self, tonic, quality, expected):
    from forge.core.executor import exec_python
    _, python_block = self._recipe_and_python()
    _, result = exec_python(
      python_block,
      inputs={"tonic": tonic, "quality": quality},
      snippet_id="build_triad",
      domains=["music"],
    )
    assert result == expected
