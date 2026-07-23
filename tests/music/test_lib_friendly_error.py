"""CW-forge-music-lib-hygiene-l531-consolidation-plus-friendly-error
(drain 2026-07-23-1310).

Follow-ups from drain 2026-07-23-1000 FEEDBACK §6. Two coupled hygiene
edits to forge/music/lib.py, both landed under one drain:

- Part A — L531 consolidation: moved `from music21 import dynamics` from
  its mid-file position (~L531 next to _VELOCITY_PROFILES) into the
  top-of-file guarded-import batch alongside sibling music21 modules.
  Test #4 (`test_dynamics_import_consolidated_at_top_of_file`) is the
  regression lock — catches accidental future re-introduction of the
  mid-file import.

- Part B — friendly runtime error: added `_require_music21()` module-
  level helper. Every chip function that dereferences music21 submodules
  now calls `_require_music21()` as its first executable line. Users
  see a friendly RuntimeError message during the transient wheel-mount
  race window instead of a raw NameError / AttributeError. Tests #1-3
  lock the helper contract and the chip-function integration.
"""
from __future__ import annotations

import inspect

import pytest

from forge.music import lib


def test_require_music21_raises_when_sentinels_are_none(monkeypatch):
  """Helper contract: when the sentinel names `note` and `stream` are
  None (wheel-not-mounted state), the helper raises RuntimeError with
  an actionable, user-friendly message."""
  monkeypatch.setattr(lib, "note", None)
  monkeypatch.setattr(lib, "stream", None)
  with pytest.raises(RuntimeError) as excinfo:
    lib._require_music21()
  msg = str(excinfo.value)
  assert "music21 is not yet mounted" in msg
  assert "retry" in msg.lower()


def test_require_music21_passes_when_sentinels_are_real(monkeypatch):
  """Happy path: when `note` and `stream` are truthy (real music21
  modules or non-None mocks), the helper returns None and does not
  raise. Guards against accidental over-restrictive checks."""
  monkeypatch.setattr(lib, "note", object())
  monkeypatch.setattr(lib, "stream", object())
  assert lib._require_music21() is None


def test_chip_function_raises_friendly_error_when_music21_absent(monkeypatch):
  """Integration test — user-facing contract lock. When a chip is
  called during the wheel-mount race window, it MUST raise the friendly
  RuntimeError from _require_music21(), NOT a raw NameError or
  AttributeError inside the chip body. `bar()` is the representative
  chip — smallest signature, most-used entry point."""
  monkeypatch.setattr(lib, "note", None)
  monkeypatch.setattr(lib, "stream", None)
  with pytest.raises(RuntimeError) as excinfo:
    lib.bar()
  assert "music21 is not yet mounted" in str(excinfo.value)


def test_dynamics_import_consolidated_at_top_of_file():
  """Part A regression lock. The BARE `from music21 import dynamics`
  (i.e., binding the module to the top-level `dynamics` name, not to
  an alias like `_dynamics_mod`) must appear exactly once in lib.py,
  and its position must be in the top-of-file guarded-import batch
  region (first 100 lines, aligned with L23-53 batch shape). Catches
  accidental future re-introduction of the pre-drain-1310 mid-file
  position at ~L531.

  Aliased-form imports (e.g., `from music21 import dynamics as
  _dynamics_mod` at ~L1699) are EXPLICITLY OUT OF SCOPE for this drain
  — they use separate names and were not the position drain 1000
  flagged for consolidation. Comment lines mentioning the phrase (e.g.,
  drain-reference markers) are ignored via the leading `#` check."""
  src = inspect.getsource(lib)
  lines = src.split("\n")

  def _is_bare_dynamics_import(ln: str) -> bool:
    stripped = ln.strip()
    if stripped.startswith("#"):
      return False
    # Match `from music21 import dynamics` NOT followed by `as`. Word
    # boundary after `dynamics` — either end of string or non-word char
    # that is not `,` (comma would mean multi-name import, still bare).
    if "from music21 import dynamics" not in stripped:
      return False
    tail = stripped.split("from music21 import dynamics", 1)[1]
    if not tail:
      return True
    # If the tail starts with word chars, it's a longer name (e.g.
    # `dynamics_extra`) — not our target.
    if tail[0].isalnum() or tail[0] == "_":
      return False
    # If it's `as ...`, that's an aliased-form — out of scope.
    if tail.strip().startswith("as "):
      return False
    return True

  hits = [
    (i + 1, ln)
    for i, ln in enumerate(lines)
    if _is_bare_dynamics_import(ln)
  ]
  assert len(hits) == 1, (
    f"Expected exactly one bare `from music21 import dynamics` in "
    f"lib.py, got {len(hits)} at lines {[h[0] for h in hits]}. "
    f"Consolidation was broken by a subsequent edit."
  )
  lineno = hits[0][0]
  assert lineno <= 100, (
    f"Bare `from music21 import dynamics` moved to line {lineno} — "
    f"expected within top-of-file batch (first 100 lines). "
    f"Consolidation was broken by a subsequent edit."
  )
