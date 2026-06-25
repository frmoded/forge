"""Music-domain globals must be lazily resolvable.

Driver smoke v0.2.169: murmuration Forge-click failed with
`NameError: play_at_offsets is not defined` inside a nested snippet
exec. Root cause: in pyodide, music21 wheels may not be loaded when
`forge.core.executor` is imported. The module's `try: from forge.music
import lib as _music_lib` block catches the ImportError and leaves
`_FORGE_MUSIC_LIB_NAMES = {}`. Later, when wheels load and the import
would succeed, the cached empty dict still wins and music chips are
never injected.

This test asserts `_domain_globals_for(["music"])` resolves chips
freshly each call so a delayed music21 import is picked up.
"""

import importlib

import pytest


def test_music_domain_globals_include_play_at_offsets():
  from forge.core import executor
  globals_dict = executor._domain_globals_for(["music"])
  assert "play_at_offsets" in globals_dict, (
    f"music-domain globals should include play_at_offsets; got keys: "
    f"{sorted(globals_dict.keys())}"
  )
  assert callable(globals_dict["play_at_offsets"])


def test_music_domain_globals_include_sequence_list():
  from forge.core import executor
  globals_dict = executor._domain_globals_for(["music"])
  assert "sequence_list" in globals_dict
  assert callable(globals_dict["sequence_list"])


def test_music_domain_globals_lazily_pick_up_late_import(monkeypatch):
  """Simulate the pyodide ordering issue: at executor-import time the
  music21 wheels aren't there yet, _FORGE_MUSIC_LIB_NAMES gets cached
  empty, then wheels load and we expect chips to become available on
  the NEXT _domain_globals_for call without re-importing executor.
  """
  from forge.core import executor

  # Force the cache empty (simulates "music21 wasn't loaded when this
  # module imported, so the try/except set _FORGE_MUSIC_LIB_NAMES = {}").
  monkeypatch.setattr(executor, "_FORGE_MUSIC_LIB_NAMES", {})
  monkeypatch.setattr(executor, "_DOMAIN_GLOBALS", {
    "music": {**executor._MUSIC21_NAMES, **{}},
    "moda": executor._FORGE_MODA_NAMES,
  })

  # First call: pre-lazy code would return empty music globals here.
  globals_dict = executor._domain_globals_for(["music"])
  # After the lazy lookup, chips should be present even though
  # _FORGE_MUSIC_LIB_NAMES at module-import time was empty.
  assert "play_at_offsets" in globals_dict, (
    "Lazy resolution should re-import forge.music.lib at call time. "
    "If this fails, executor._domain_globals_for is still using the "
    "stale _FORGE_MUSIC_LIB_NAMES from import time."
  )
