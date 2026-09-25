"""Drain 2026-09-26-0310 — the `length_of` core chip.

The V2 Recipe grammar's only chip-call form in EXPRESSION position is
`Call [[name]] with k=v` (kwargs only). Python's `len` takes a positional
argument, so there was no valid way to bind "how many items" to a variable:
`Let n = [[len]] items.` is a parse error (the `[[chip]] <expr>.` shorthand
is statement-only and discards its value) and `Call [[len]] with obj=items.`
compiles to `len(obj=items)`, a runtime TypeError. `length_of` is the
kwargs-callable chip for that: `Let n = Call [[length_of]] with items=items.`
"""
import inspect

import pytest

from forge.core.executor import _DOMAIN_GLOBALS, _FORGE_CORE_LIB_NAMES
from forge.core.lib import length_of


class TestLengthOf:
  def test_counts_a_list(self):
    assert length_of([]) == 0
    assert length_of(["a", "b", "c"]) == 3

  def test_counts_other_sized_things(self):
    assert length_of("hello") == 5
    assert length_of((1, 2)) == 2
    assert length_of({"a": 1, "b": 2}) == 2

  def test_returns_an_int(self):
    assert type(length_of([1, 2, 3])) is int

  def test_the_parameter_is_named_items_and_callable_by_keyword(self):
    # The Recipe call form is kwargs-only: `Call [[length_of]] with items=...`.
    assert list(inspect.signature(length_of).parameters) == ["items"]
    assert length_of(items=[1, 2, 3, 4]) == 4

  def test_a_value_with_no_length_raises_typeerror_like_len(self):
    with pytest.raises(TypeError):
      length_of(5)


class TestRegistration:
  def test_registered_in_the_core_lib_names(self):
    assert _FORGE_CORE_LIB_NAMES["length_of"] is length_of

  def test_reaches_every_domain_bundle(self):
    # Core chips merge into EVERY domain's globals, so `[[length_of]]`
    # resolves whichever domain a vault declares.
    for domain, names in _DOMAIN_GLOBALS.items():
      assert names.get("length_of") is length_of, domain
