"""Tests for `forge.music.lib.grade_scale_attempt` and `render_graded_scale`.

CW 1655 — sibling to build_chord (drain 1210) / build_triad_chord
(drain 1245). Extracted from a `{{ }}` value slot inline inside
construct_c_major_piano.md's Recipe: a full lambda building a
music21 Part, grading the attempt, and inserting the verdict as a
TextExpression. Grading is pure Python (no music21 dependency); the
lambda's zip()-truncation quirk (missing/extra notes past the
shorter list's length never appear in "wrong at position(s)", only in
the "You entered N note(s)" count message) is preserved exactly, not
fixed — confirmed against the ORIGINAL slot logic run in isolation
before writing these expectations, not re-derived from the wording.
"""
import pytest

from forge.music import lib

music21 = pytest.importorskip("music21")

CORRECT = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]


class TestGradeScaleAttempt:
  def test_exact_match(self):
    assert lib.grade_scale_attempt(CORRECT, CORRECT) == (
      "Correct! You built the full C major scale, tonic to tonic."
    )

  def test_octave_insensitive_exact_match(self):
    """A right pitch-class at ANY octave counts as correct — the
    original slot's rstrip("0123456789") behavior, preserved."""
    guess = ["C5", "D4", "E4", "F4", "G4", "A4", "B4", "C6"]
    assert lib.grade_scale_attempt(guess, CORRECT) == (
      "Correct! You built the full C major scale, tonic to tonic."
    )

  def test_fewer_notes(self):
    assert lib.grade_scale_attempt(CORRECT[:5], CORRECT) == (
      "You entered 5 note(s); the scale needs 8. "
      "Not yet - wrong at position(s): []"
    )

  def test_more_notes(self):
    assert lib.grade_scale_attempt(CORRECT + ["D5"], CORRECT) == (
      "You entered 9 note(s); the scale needs 8. "
      "Not yet - wrong at position(s): []"
    )

  def test_right_count_wrong_positions(self):
    guess = ["C4", "D4", "X4", "F4", "Y4", "A4", "B4", "C5"]
    assert lib.grade_scale_attempt(guess, CORRECT) == (
      "Not yet - wrong at position(s): [3, 5]"
    )

  def test_zip_truncation_quirk_preserved_not_fixed(self):
    """Genuinely-missing trailing positions never appear in the
    wrong-position list when guess is shorter than correct — this is
    the ORIGINAL slot's behavior (zip() stops at the shorter
    sequence), not a new bug. Confirmed against the live slot logic
    before writing this test; preserved verbatim, not redesigned."""
    guess = ["X4", "D4", "E4"]  # wrong at 1, then missing 4 notes
    result = lib.grade_scale_attempt(guess, CORRECT)
    assert "You entered 3 note(s); the scale needs 8." in result
    assert "position(s): [1]" in result  # NOT [1, 4, 5, 6, 7, 8]


class TestRenderGradedScale:
  def test_returns_a_part(self):
    part = lib.render_graded_scale(CORRECT, "some verdict")
    assert isinstance(part, music21.stream.Part)

  def test_notes_match_guess_in_order(self):
    part = lib.render_graded_scale(CORRECT, "some verdict")
    assert [n.nameWithOctave for n in part.notes] == CORRECT

  def test_verdict_is_a_text_expression_at_the_start(self):
    part = lib.render_graded_scale(CORRECT, "You did it!")
    elements = list(part)
    assert isinstance(elements[0], music21.expressions.TextExpression)
    assert elements[0].content == "You did it!"
    assert elements[0].offset == 0.0


def test_registered_in_both_executor_chip_lists():
  from forge.core import executor
  for name in ("grade_scale_attempt", "render_graded_scale"):
    assert executor._FORGE_MUSIC_LIB_NAMES[name].__qualname__ == name
    assert name in executor._MUSIC_LAZY_CHIP_NAMES


class TestConstructCMajorPianoNoteRegression:
  """End-to-end: the actual `construct_c_major_piano.md` note, real
  parse + transpile + exec — per the standing "works/verified claims
  must be tested through the real production entry point" rule."""

  NOTE_PATH = (
    "/Users/odedfuhrmann/projects/music-theory/theory_exercises/"
    "construct_c_major_piano.md"
  )

  def _recipe_and_python(self):
    import re
    text = open(self.NOTE_PATH, encoding="utf-8").read()
    recipe = re.search(
      r"^# Recipe\s*\n\n(.*?)(?:\n\n# Python|\Z)", text, re.S | re.M
    ).group(1)
    python_match = re.search(
      r"^# Python\s*\n\n```python\n(.*?)\n```", text, re.S | re.M)
    python_block = python_match.group(1) if python_match else None
    return recipe, python_block

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

  def test_note_executes_correctly_exact_match(self):
    from forge.core.executor import exec_python
    _, python_block = self._recipe_and_python()
    _, result = exec_python(
      python_block,
      inputs={"guess": CORRECT},
      snippet_id="construct_c_major_piano",
      domains=["music"],
    )
    assert isinstance(result, music21.stream.Part)
    text_expr = list(result)[0]
    assert isinstance(text_expr, music21.expressions.TextExpression)
    assert text_expr.content == (
      "Correct! You built the full C major scale, tonic to tonic."
    )

  def test_note_executes_correctly_wrong_answer(self):
    """Wrong answer, but every pitch must still be a REAL music21
    pitch name — unlike grade_scale_attempt (pure string comparison,
    doesn't care whether a placeholder is "valid"), render_graded_scale
    constructs an actual Note from every guess element, so a garbage
    placeholder like "X4" fails at rendering, not grading. Caught live
    while writing this test: the first version used "X4"/"Y4" (fine
    for the pure grading unit tests above, which never render) and hit
    a real music21 "Cannot make a step out of 'X'" error here."""
    from forge.core.executor import exec_python
    _, python_block = self._recipe_and_python()
    guess = ["D4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
    _, result = exec_python(
      python_block,
      inputs={"guess": guess},
      snippet_id="construct_c_major_piano",
      domains=["music"],
    )
    text_expr = list(result)[0]
    assert text_expr.content == "Not yet - wrong at position(s): [1]"
