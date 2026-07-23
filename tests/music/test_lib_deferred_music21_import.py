"""CW-forge-music-lib-defer-music21-imports (drain 2026-07-23-1000).

Regression lock: `forge.music.lib` MUST import cleanly even when
music21 is not available at import time. The pyodide runtime mounts
the music21 wheel LATE — after `forge.core.executor` loads and
after the first `_domain_globals_for('music')` lazy-hydration retry
in some code paths — and prior to this drain the unguarded top-level
`from music21 import clef, instrument, key, meter, note, pitch, stream`
at lib.py:23 blew up the entire music authoring loop in v0.2.298.

These tests use `sys.modules` monkey-patching to simulate the
music21-unavailable state that pyodide exhibits at first executor
load. The fix guards L23 with `try/except ImportError` and adjusts
L60's `StreamLike` module-level expression to survive the None
fallback (both are pure load-time survival — actual call-time use
of the chip functions still requires music21 to be present, which
the surrounding executor lazy-hydration ensures).
"""
from __future__ import annotations

import importlib
import sys

import pytest


def _evict_forge_music(monkeypatch):
  """Remove any cached `forge.music*` modules so a fresh import re-
  executes the top-level. Python's import machinery caches partial
  modules on failed import unless we clean up explicitly."""
  for name in list(sys.modules.keys()):
    if name.startswith("forge.music"):
      monkeypatch.delitem(sys.modules, name, raising=False)


def test_forge_music_lib_import_succeeds_when_music21_absent(monkeypatch):
  """The failing test that anchors the fix. Simulates music21 being
  unavailable at first executor-load time — the pyodide wheel-not-
  mounted-yet scenario. Import MUST succeed; the fallback bindings
  must not break StreamLike or any other module-level expression.

  Pre-fix: ImportError at lib.py:23 → whole plugin music loop dead.
  Post-fix: import completes; names bound to None.
  """
  _evict_forge_music(monkeypatch)
  # Block music21 import — same shape as pyodide's wheel-not-mounted.
  monkeypatch.setitem(sys.modules, "music21", None)
  # Should not raise.
  lib = importlib.import_module("forge.music.lib")
  assert lib is not None
  # StreamLike survives the None fallback for module-level type-alias
  # use (drain 2005-B StreamLike guard).
  assert hasattr(lib, "StreamLike")


def test_forge_music_lib_functions_work_when_music21_mounted(monkeypatch):
  """Regression lock: normal path still works. When music21 IS
  present, the module imports fully and chip functions are callable.
  Skipped in dev envs without music21 (import will surface the miss
  cleanly)."""
  music21 = pytest.importorskip("music21")
  _evict_forge_music(monkeypatch)
  monkeypatch.delitem(sys.modules, "music21", raising=False)
  # Let the real music21 back in.
  sys.modules["music21"] = music21
  lib = importlib.import_module("forge.music.lib")
  # Sanity — the seven names bind to real music21 submodules.
  assert lib.stream is music21.stream
  assert lib.note is music21.note
  assert lib.pitch is music21.pitch
  # A representative chip function is callable.
  result = lib.bar(lib.note.Note("C4", quarterLength=1.0))
  assert result is not None


def test_executor_loads_cleanly_when_music21_absent(monkeypatch):
  """Executor MUST import cleanly even when music21 is unavailable.
  Post-fix: forge.music.lib imports successfully with `stream=None`
  etc, so the executor's eager `from forge.music import lib as
  _music_lib` at L33 SUCCEEDS and `_FORGE_MUSIC_LIB_NAMES` populates
  with chip callables. Drain-2020's drift guard then fires the SAME
  set-equality check as it does when music21 IS available, and passes
  (both dicts + tuple stay in sync)."""
  _evict_forge_music(monkeypatch)
  monkeypatch.delitem(sys.modules, "forge.core.executor", raising=False)
  monkeypatch.setitem(sys.modules, "music21", None)
  # Should not raise RuntimeError from the drift guard.
  executor = importlib.import_module("forge.core.executor")
  # Post-fix: chip names ARE populated (even though the underlying
  # music21 calls will fail if invoked before music21 mounts).
  assert "closed_hihat" in executor._FORGE_MUSIC_LIB_NAMES
  assert isinstance(executor._MUSIC_LAZY_CHIP_NAMES, tuple)
  assert "closed_hihat" in executor._MUSIC_LAZY_CHIP_NAMES
  # Drift guard passes — eager keys match lazy tuple.
  assert set(executor._FORGE_MUSIC_LIB_NAMES.keys()) == set(
    executor._MUSIC_LAZY_CHIP_NAMES
  )
