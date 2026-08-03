"""Domain-agnostic library-note primitives for E-- Recipes.

Drain 2026-07-26-1000 — first entries: `nth` (single-element indexing)
and `pick_indices` (multi-element pick). Both are trivial wrappers over
Python list access, exposed as library notes so Recipes can index/slice
via `[[nth]]` / `[[pick_indices]]` wikilinks instead of falling back to
`{{ ... }}` code slots.

These are the peer implementations for the v2-spec-working.md L74 design
intent: "List operations → library chips (`[[append_to]]`, `[[first]]`,
etc.), NOT new E-- grammar." (Neither `first` nor `append_to` has landed
yet as of drain 2026-07-26-1000; future utility primitives should live
in this same file.)

Registration surface: this module is treated as a special
"core" pseudo-domain that auto-includes in EVERY domain's
callable set (music, moda, and any future domains). Mirrors the
`_TUTORIAL_CHIPS` precedent in
forge-transpile/engine_chip_introspector.py, which surfaces Python
builtins (like `print`) unconditionally regardless of the caller's
`active_domains` filter. The engine-side merge lives in
forge/core/executor.py — see `_FORGE_CORE_LIB_NAMES`.
"""
from __future__ import annotations

from typing import Sequence, TypeVar

_T = TypeVar("_T")


def nth(lst: Sequence[_T], index: int) -> _T:
  """Return the element at position `index` in `lst` (0-indexed).

  Semantics match Python's `lst[index]` exactly: negative indices count
  from the end (`nth(lst, -1)` is the last element), and an out-of-range
  index raises `IndexError` — no silent None fallback.

  Example: `nth(["a", "b", "c"], 1)` → `"b"`.
  """
  return lst[index]


def pick_indices(lst: Sequence[_T], indices: Sequence[int]) -> list[_T]:
  """Return a new list of the elements at `indices` in `lst`.

  Semantics: `[lst[i] for i in indices]`. Negative indices are honored
  (Python semantics). Out-of-range indices propagate `IndexError` from
  the offending `lst[i]` access — no silent skipping.

  Example: `pick_indices(["a", "b", "c", "d", "e"], [0, 2, 4])`
  → `["a", "c", "e"]`.
  """
  return [lst[i] for i in indices]


def mcq(
  question: str,
  choices: Sequence[str],
  correct_index: int,
  guess: int,
  explanation: str = "",
) -> str:
  """Score a multiple-choice question and return cohort-facing feedback.

  Drain 2026-08-03-1125, from MCQ brainstorm B1 approach 3. Pairs with
  the `input_enums:` dropdown shipped in drain 2026-07-31-1120: the
  cohort picks a choice from the dropdown, the Recipe converts it to an
  index, and this returns the verdict.

  Domain-agnostic on purpose — this lives in `forge.core.lib`, not
  `forge.music.lib`, because a multiple-choice question is about the
  interaction shape, not the subject. Music, maths and prose questions
  all use the same primitive.

  `question` is accepted so the note's Recipe names the question in one
  place, and so a future scored-quiz primitive can aggregate calls
  without re-reading the Description. It is deliberately NOT echoed back
  in the feedback: the cohort is looking at the question on screen, and
  repeating it just pushes the verdict down.

  Example: `mcq("...", ["major", "minor"], 0, 1, "See [[scale]].")`
  → `"✗ Not quite. You picked 'minor'; the correct answer is 'major'.
  See [[scale]]."`
  """
  opts = list(choices)
  if len(opts) < 2:
    raise ValueError(
      f"mcq needs at least 2 choices to be a choice; got {len(opts)}"
    )
  for label, value in (("correct_index", correct_index), ("guess", guess)):
    if isinstance(value, bool) or not isinstance(value, int):
      raise ValueError(
        f"mcq {label} must be an int index into choices, got {value!r}"
      )
    # Negative indices are rejected rather than honored (unlike `nth`):
    # a negative answer index is a Recipe bug, and Python's wrap-around
    # would silently mark a wrong answer correct.
    if not 0 <= value < len(opts):
      raise ValueError(
        f"mcq {label}={value} is out of range for {len(opts)} choices "
        f"(valid: 0..{len(opts) - 1})"
      )

  if guess == correct_index:
    return f"✓ Correct — {opts[correct_index]}."
  base = (
    f"✗ Not quite. You picked {opts[guess]!r}; the correct answer is "
    f"{opts[correct_index]!r}."
  )
  return f"{base} {explanation}" if explanation else base
