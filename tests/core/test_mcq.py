"""Drain 2026-08-03-1125 — the `[[mcq]]` core library note.

Multiple-choice scoring, paired with the `input_enums:` dropdown from
drain 2026-07-31-1120. Lives in `forge.core.lib` because the primitive
is about the interaction shape, not the subject matter.
"""

from __future__ import annotations

import pytest

from forge.core.executor import _FORGE_CORE_LIB_NAMES
from forge.core.lib import mcq

CHOICES = ["major", "minor", "diminished", "augmented"]


def test_correct_answer_names_the_choice():
  out = mcq("Which quality?", CHOICES, correct_index=0, guess=0)
  assert out == "✓ Correct — major."


def test_wrong_answer_shows_both_picked_and_correct():
  out = mcq("Which quality?", CHOICES, correct_index=0, guess=1)
  assert "Not quite" in out
  assert "'minor'" in out, "must name what the cohort picked"
  assert "'major'" in out, "must name the correct answer"


def test_explanation_appended_only_on_wrong_answers():
  hint = "See [[music_theory/scales/scale]]."
  wrong = mcq("Q", CHOICES, correct_index=0, guess=2, explanation=hint)
  assert wrong.endswith(hint)

  # A correct answer doesn't need the remedial pointer — appending it
  # would read as though the cohort had got it wrong.
  right = mcq("Q", CHOICES, correct_index=0, guess=0, explanation=hint)
  assert hint not in right


def test_no_explanation_leaves_no_trailing_space():
  out = mcq("Q", CHOICES, correct_index=0, guess=1)
  assert out == out.rstrip(), f"trailing whitespace in {out!r}"


@pytest.mark.parametrize("bad", [-1, 4, 99])
def test_out_of_range_guess_is_rejected(bad):
  with pytest.raises(ValueError, match="guess"):
    mcq("Q", CHOICES, correct_index=0, guess=bad)


@pytest.mark.parametrize("bad", [-1, 4, 99])
def test_out_of_range_correct_index_is_rejected(bad):
  with pytest.raises(ValueError, match="correct_index"):
    mcq("Q", CHOICES, correct_index=bad, guess=0)


def test_negative_index_is_rejected_not_wrapped():
  """`nth` honours Python's negative indexing; mcq must NOT.

  With wrap-around, `guess=-1` on a 4-choice question would silently
  match `correct_index=3` and mark a bug as a correct answer.
  """
  with pytest.raises(ValueError):
    mcq("Q", CHOICES, correct_index=3, guess=-1)


@pytest.mark.parametrize("choices", [[], ["only one"]])
def test_fewer_than_two_choices_is_rejected(choices):
  with pytest.raises(ValueError, match="at least 2 choices"):
    mcq("Q", choices, correct_index=0, guess=0)


@pytest.mark.parametrize("bad", [True, False, 1.0, "0", None])
def test_non_int_indices_are_rejected(bad):
  """`True` is an int subclass in Python and would index as 1 — an
  enum-to-index conversion that produced a bool is a Recipe bug."""
  with pytest.raises(ValueError):
    mcq("Q", CHOICES, correct_index=0, guess=bad)


def test_two_choice_case_works_as_true_false():
  """§Not in scope routes true/false through mcq rather than a separate
  primitive; pin that it actually works."""
  assert mcq("Q", ["true", "false"], 0, 0) == "✓ Correct — true."


def test_registered_in_the_core_domain():
  """Core lib names auto-include in EVERY domain's callable set, so
  `[[mcq]]` must resolve from music, moda and future domains alike."""
  assert "mcq" in _FORGE_CORE_LIB_NAMES
  assert _FORGE_CORE_LIB_NAMES["mcq"] is mcq
