"""Discipline check: every variadic-positional engine chip in
forge.music.lib + forge.moda.lib must have a `<name>_list` companion.

V2 Recipe is kwarg-only (`Call [[name]] with k=v.`), so a chip whose
signature is `def name(*items, ...)` is unreachable from cohort
authoring. The convention is to ship a `name_list(items, ...)` wrapper
that unpacks the list into the variadic call:

    def voices_list(sections):
      return voices(*sections)

Per v0.2.220 forge-music V1→V2 migration: `voices(*streams)` had no
wrapper, blocking song.md migration. v0.2.222: added `voices_list`.
v0.2.226: added `bar_list` (this prompt's audit) so cohort can use
`[[bar_list]]` from V2 Recipes.

This test prevents the next surprise: any new variadic-positional
chip added to either lib MUST ship with a `_list` companion. If a
future commit adds `def foo(*items)` without `foo_list`, the suite
goes red, the chip stays unreachable from V2 cohort authoring no
longer.
"""
import inspect


def _audit_module(module, label):
  """Return list of (chip_name, error_message) for chips that violate
  the discipline. Empty list means clean."""
  violations = []
  for name in dir(module):
    if name.startswith("_"):
      continue
    obj = getattr(module, name)
    if not callable(obj) or not inspect.isfunction(obj):
      continue
    try:
      sig = inspect.signature(obj)
    except (ValueError, TypeError):
      continue
    has_variadic_positional = any(
      p.kind == inspect.Parameter.VAR_POSITIONAL
      for p in sig.parameters.values()
    )
    if not has_variadic_positional:
      continue
    expected = f"{name}_list"
    if not hasattr(module, expected):
      violations.append(
        (name, (
          f"forge.{label}.lib.{name} is variadic-positional "
          f"({sig}) but has no {expected}(items, ...) companion. "
          f"V2 Recipe is kwarg-only — cohort can't reach this chip "
          f"without the wrapper. See voices_list / sequence_list / "
          f"bar_list for the reference shape."
        ))
      )
  return violations


def test_forge_music_lib_variadic_chips_have_list_wrappers():
  from forge.music import lib as music_lib
  violations = _audit_module(music_lib, "music")
  assert violations == [], (
    "Variadic-positional chip(s) missing _list companion:\n"
    + "\n".join(f"  - {msg}" for _, msg in violations)
  )


def test_forge_moda_lib_variadic_chips_have_list_wrappers():
  from forge.moda import lib as moda_lib
  violations = _audit_module(moda_lib, "moda")
  assert violations == [], (
    "Variadic-positional chip(s) missing _list companion:\n"
    + "\n".join(f"  - {msg}" for _, msg in violations)
  )


def test_known_list_wrappers_exist():
  """Spot-check the three list wrappers that exist today are reachable
  via the lib module's public API (not just inside the file). Guards
  against accidental rename / private-ification."""
  from forge.music import lib as music_lib
  for name in ("sequence_list", "voices_list", "bar_list"):
    assert hasattr(music_lib, name), f"forge.music.lib.{name} missing"
    fn = getattr(music_lib, name)
    assert callable(fn), f"forge.music.lib.{name} not callable"
