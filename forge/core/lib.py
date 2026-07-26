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
