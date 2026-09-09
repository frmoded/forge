"""Tests for `forge.music.lib.build_chord`.

CW 1210 — shared music21 chord-building library note, replacing the
`{{ }}` value slot previously duplicated inline inside
`music-theory/theory_exercises/build_seventh_chord.md`'s Recipe. A `{{ }}`
slot holds a literal Python comprehension there rather than a
natural-language request — this chip removes the slot entirely by giving
the Recipe a real, grammar-legal `Call [[build_chord]]` target.

Pitch spellings below are the actual music21 output for `tonic="C4"`,
computed directly rather than hand-guessed (music21's flat convention is
`-`, not `b` — e.g. `"B-4"` not `"Bb4"`).
"""
import re

import pytest

from forge.music import lib

music21 = pytest.importorskip("music21")


class TestBuildChord:
  def test_maj7(self):
    assert lib.build_chord("C4", "maj7") == ["C4", "E4", "G4", "B4"]

  def test_dom7(self):
    assert lib.build_chord("C4", "dom7") == ["C4", "E4", "G4", "B-4"]

  def test_min7(self):
    assert lib.build_chord("C4", "min7") == ["C4", "E-4", "G4", "B-4"]

  def test_half_dim7(self):
    assert lib.build_chord("C4", "half_dim7") == ["C4", "E-4", "G-4", "B-4"]

  def test_dim7(self):
    assert lib.build_chord("C4", "dim7") == ["C4", "E-4", "G-4", "B--4"]

  def test_dom9(self):
    assert lib.build_chord("C4", "dom9") == ["C4", "E4", "G4", "B-4", "D5"]

  def test_dom11(self):
    assert lib.build_chord("C4", "dom11") == \
      ["C4", "E4", "G4", "B-4", "D5", "F5"]

  def test_dom13(self):
    assert lib.build_chord("C4", "dom13") == \
      ["C4", "E4", "G4", "B-4", "D5", "F5", "A5"]

  def test_different_tonic(self):
    # Sanity that `tonic` is actually threaded through, not hardcoded.
    assert lib.build_chord("D4", "maj7") == ["D4", "F#4", "A4", "C#5"]

  def test_unknown_quality_names_it_and_the_choices(self):
    with pytest.raises(KeyError):
      lib.build_chord("C4", "not-a-quality")


def test_registered_in_both_executor_chip_lists():
  """Per drain 2026-08-05-0620's lesson (re-verified live in
  test_lib_melodic_line.py): shipping the function without registering it
  in BOTH lists is the failure mode, and only one of the two fails loudly
  (the drift guard at executor.py import time catches the other)."""
  from forge.core import executor
  assert executor._FORGE_MUSIC_LIB_NAMES["build_chord"].__qualname__ == \
    "build_chord"
  assert "build_chord" in executor._MUSIC_LAZY_CHIP_NAMES


class TestBuildSeventhChordNoteRegression:
  """End-to-end: the actual `build_seventh_chord.md` note, real parse +
  transpile + exec, not just a call to `build_chord` in isolation — per
  the standing "works/verified claims must be tested through the real
  production entry point" rule.
  """

  NOTE_PATH = (
    "/Users/odedfuhrmann/projects/music-theory/theory_exercises/"
    "build_seventh_chord.md"
  )

  def _recipe_and_python(self):
    text = open(self.NOTE_PATH, encoding="utf-8").read()
    recipe = re.search(
      r"^# Recipe\s*\n\n(.*?)\n\n# Python", text, re.S | re.M).group(1)
    python_block = re.search(
      r"^# Python\s*\n\n```python\n(.*?)\n```", text, re.S | re.M).group(1)
    return recipe, python_block

  def test_recipe_has_no_slot_markers(self):
    recipe, _ = self._recipe_and_python()
    assert "{{" not in recipe and "}}" not in recipe

  def test_stored_python_is_byte_exact_fresh_transpile(self):
    from forge.recipe.parser import parse
    from forge.recipe.transpiler import transpile
    recipe, python_block = self._recipe_and_python()
    transpiled = transpile(parse(recipe), resolve_slot=None)
    assert transpiled.strip() == python_block.strip()

  @pytest.mark.parametrize("tonic,quality,expected", [
    ("C4", "dom7", ["C4", "E4", "G4", "B-4"]),
    ("C4", "maj7", ["C4", "E4", "G4", "B4"]),
  ])
  def test_note_executes_correctly_end_to_end(self, tonic, quality, expected):
    from forge.core.executor import exec_python
    _, python_block = self._recipe_and_python()
    _, result = exec_python(
      python_block,
      inputs={"tonic": tonic, "quality": quality},
      snippet_id="build_seventh_chord",
      domains=["music"],
    )
    assert result == expected
