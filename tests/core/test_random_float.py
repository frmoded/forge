"""Drain 2026-08-24-0910 — the `random_float` core chip.

`[[random]]` is illegal vocabulary: nothing registers it, and the base
global it collides with is Python's `random` MODULE, so `random()`
raises `'module' object is not callable` (live-proven in Pyodide
against the driver's own build, drain 2010). Meanwhile /generate kept
emitting `# missing chip: random_float — return a random float between
0.0 and 1.0` on its own — three independent times across two days
(drain 2000's calls, and drain 0900's calls 1 and 2). This is the
system naming its own vocabulary gap.
"""

import inspect

from forge.core import lib as core_lib
from forge.core.executor import _DOMAIN_GLOBALS, _FORGE_CORE_LIB_NAMES
from forge.core.lib import random_float


class TestRandomFloat:
  def test_returns_a_float_in_the_unit_interval(self):
    for _ in range(200):
      v = random_float()
      assert isinstance(v, float)
      assert 0.0 <= v < 1.0, v

  def test_successive_calls_differ(self):
    # NON-VACUITY for "random": a constant would satisfy the range
    # assertion above forever. 200 draws colliding on one value has
    # probability ~0 for a real uniform source.
    assert len({random_float() for _ in range(200)}) > 1

  def test_takes_no_arguments(self):
    # The E-- call form is `Call [[random_float]] with.` — kwargs-only
    # dispatch with nothing to pass. A signature that grew a required
    # parameter would make that call form a TypeError at runtime.
    sig = inspect.signature(random_float)
    assert list(sig.parameters) == []


class TestRegistration:
  def test_registered_as_a_core_chip(self):
    assert _FORGE_CORE_LIB_NAMES["random_float"] is random_float

  def test_reaches_every_domain(self):
    # Core chips merge into EVERY domain bundle, so a domain-narrowed
    # vault still has the word.
    for domain, bundle in _DOMAIN_GLOBALS.items():
      assert bundle.get("random_float") is random_float, domain

  def test_does_not_shadow_the_stdlib_random_module(self):
    # The founding incident: the name `random` collides with the
    # always-injected stdlib module. Naming the chip `random` would
    # have reproduced it (§8).
    assert "random" not in _FORGE_CORE_LIB_NAMES


class TestCoreLibRegistrationIsComplete:
  """§8 — 'don't hand-list it into any registration the guards derive.'

  `_FORGE_CORE_LIB_NAMES` is a hand-written dict, and nothing checked
  it against the module it mirrors, so a future core chip could land in
  lib.py and silently never be callable from a Recipe. This derives the
  expected set from the module and compares.
  """

  @staticmethod
  def _public_callables():
    return {
      name for name, obj in vars(core_lib).items()
      if callable(obj)
      and not name.startswith("_")
      and getattr(obj, "__module__", None) == core_lib.__name__
    }

  def test_every_public_core_lib_callable_is_registered(self):
    missing = sorted(self._public_callables() - set(_FORGE_CORE_LIB_NAMES))
    assert missing == [], (
      f"public callables in forge.core.lib that no Recipe can reach: "
      f"{missing}")

  def test_the_deriver_actually_finds_callables(self):
    # NON-VACUITY: a deriver that returned an empty set would make the
    # comparison above pass no matter what was missing.
    found = self._public_callables()
    assert {"nth", "pick_indices"} <= found, sorted(found)


class TestDocstringIsCohortFacing:
  """The docstring is not internal documentation.

  forge-transpile's AST introspector reads it verbatim into the
  /generate chip catalog (so it goes to the LLM on every call) and it
  surfaces to cohort members as the chip's docs. Drain rationale and
  incident history belong in comments above the def, where this drain
  put them after seeing the first draft come back in the catalog dump.
  """

  def test_docstring_carries_no_engineering_rationale(self):
    doc = random_float.__doc__ or ""
    for leak in ("Drain 20", "stdlib", "executor.py", "module' object"):
      assert leak not in doc, f"{leak!r} leaks into the cohort-facing docstring"

  def test_docstring_says_what_it_returns_and_that_it_varies(self):
    # NON-VACUITY for the test above: a docstring emptied to satisfy
    # the leak check would pass it and teach nothing.
    doc = random_float.__doc__ or ""
    assert "between 0 and 1" in doc
    assert "every call" in doc
