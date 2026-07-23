"""Drift guard: eager _FORGE_*_LIB_NAMES dict vs lazy _*_LAZY_CHIP_NAMES.

Drain 1500's `major_scale` defect landed because the two parallel
chip lists in `forge.core.executor` silently disagreed by 5 chips
(walking_bass_line, piano_voicing, violin_bowing, vocal_line,
major_scale) — the eager module-level import dict was updated but the
lazy `_register_domain` hardcoded fallback list was not. Drain
2026-07-22-2020 extracted the lazy list to a module-level constant
and added a module-level `raise RuntimeError` at import time.

These tests are the PRIMARY guard against recurrence:

- test_executor_music_eager_dict_matches_lazy_list — positive check.
- test_executor_moda_eager_dict_matches_lazy_list — positive check
  for the parallel moda structure.
- test_executor_drift_detected_when_list_out_of_date — mutation test
  proves the equality check actually catches drift, not just passes
  by coincidence.

The module-level `raise RuntimeError` is defense-in-depth for runtime
imports outside the test harness (production, `pytest -O`).
"""
from __future__ import annotations


def test_executor_music_eager_dict_matches_lazy_list():
  """The music chip eager dict at executor.py L34-89 and the lazy
  hydration name tuple _MUSIC_LAZY_CHIP_NAMES MUST cover the same
  chip set. Any drift breaks the lazy hydration path (partial-wheel
  install, missing sibling module at bootstrap → dropped chips)."""
  from forge.core import executor
  eager_keys = set(executor._FORGE_MUSIC_LIB_NAMES.keys())
  lazy_names = set(executor._MUSIC_LAZY_CHIP_NAMES)
  missing_from_lazy = eager_keys - lazy_names
  missing_from_eager = lazy_names - eager_keys
  assert not missing_from_lazy, (
    f"executor music chip list drift: eager dict has chips the lazy "
    f"list does not: {sorted(missing_from_lazy)}"
  )
  assert not missing_from_eager, (
    f"executor music chip list drift: lazy list has chips the eager "
    f"dict does not: {sorted(missing_from_eager)}"
  )


def test_executor_moda_eager_dict_matches_lazy_list():
  """Same invariant for the parallel moda-domain pair."""
  from forge.core import executor
  eager_keys = set(executor._FORGE_MODA_LIB_NAMES.keys())
  lazy_names = set(executor._MODA_LAZY_CHIP_NAMES)
  missing_from_lazy = eager_keys - lazy_names
  missing_from_eager = lazy_names - eager_keys
  assert not missing_from_lazy, (
    f"executor moda chip list drift: eager dict has chips the lazy "
    f"list does not: {sorted(missing_from_lazy)}"
  )
  assert not missing_from_eager, (
    f"executor moda chip list drift: lazy list has chips the eager "
    f"dict does not: {sorted(missing_from_eager)}"
  )


def test_executor_drift_detected_when_list_out_of_date():
  """Mutation test: inject a fake chip into the eager dict and confirm
  the equality check flags the drift. Proves the drift-detection
  logic actually detects drift, not just passes by coincidence."""
  from forge.core import executor
  fake_eager = dict(executor._FORGE_MUSIC_LIB_NAMES)
  fake_chip_name = "deliberately_synthetic_chip_that_should_not_exist"
  fake_eager[fake_chip_name] = lambda: None
  eager_keys = set(fake_eager.keys())
  lazy_names = set(executor._MUSIC_LAZY_CHIP_NAMES)
  assert eager_keys - lazy_names == {fake_chip_name}, (
    f"drift-detection logic failed to identify the injected fake chip; "
    f"got difference {eager_keys - lazy_names!r}"
  )
