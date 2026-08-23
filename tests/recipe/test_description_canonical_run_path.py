"""Drain 2026-08-24-2330 — the run path for a Description-canonical,
slot-bearing note with a NESTED id.

THE INCIDENT. The driver's `authoring/random_note` failed every run on
plugin v0.2.366 with `Empty or missing Python code for
'authoring/random_note'`. The plugin's Description-canonical branch had
started passing `canonical_layer='description'` (its drain 1600 threaded
the note's facet through so the ERROR MESSAGE could name the right
facet), and this module's `layer == "description": return None`
short-circuit answered with no code at all.

WHAT THESE TESTS PIN. The client now sends no routing layer from that
branch (`engineRoutingLayer`, plugin-side), so what the engine sees for
the driver's note is the no-layer call. These pin what the engine must
do with it — this is the contract the client fix depends on, and if it
ever changes, the client's Description-canonical run silently breaks
again.

The nested id is not decoration. It is the shape that failed, and it is
carried through every test here on purpose: the slot machinery keys its
cache by `(slot_text, snippet_id)`, so a bare-id test would not exercise
the same keys the driver's note produces.
"""

import pytest

from forge.core.executor import exec_python, resolve_action_code
from forge.core.slot_cache import SlotCacheMissError, compute_slot_cache_key

# The driver's note, verbatim in shape: Description-canonical, a
# slot-bearing Recipe, a stale Python facet from the previous
# generation, and a nested snippet id.
NESTED_ID = "authoring/random_note"

DRIVER_BODY = """---
type: action
source_facet: description
---

# Description

A random number between 0 and 2, multiplied by an input scale.

# Recipe

Input scale: float = 1.0.
Let raw = {{ a random float between 0 and 1 }}.
Let scaled = raw * 2.
Let result = scaled * scale.
Return result.

# Python

def compute(context):
    return 41
"""


def _driver_snip():
  return {
    "snippet_id": NESTED_ID,
    "body": DRIVER_BODY,
    "meta": {"type": "action", "source_facet": "description"},
  }


def test_no_routing_layer_raises_slot_miss_not_none():
  """THE REGRESSION GUARD — fails on the original incident.

  With no routing layer the engine must reach the Recipe and report the
  unresolved slot. Returning None here is what reached `exec_python` as
  empty code and produced the driver's error.
  """
  with pytest.raises(SlotCacheMissError) as excinfo:
    resolve_action_code(_driver_snip())
  assert NESTED_ID in str(excinfo.value)


def test_description_routing_layer_still_returns_none():
  """The behaviour the client must not trigger, pinned as-is.

  This is NOT an endorsement — it is the reason the client-side fix
  exists. Recording it means a future reader can see that the engine
  branch is intact and that the client is what changed. If this branch
  is ever retired engine-side, this test is the one to delete, and its
  failure will say so out loud.
  """
  assert resolve_action_code(_driver_snip(), canonical_layer="description") is None


def test_that_none_is_exactly_what_produced_the_drivers_error():
  """Closes the loop between the None above and the reported message.

  Without this, the two facts (`returns None` / `driver saw empty-code`)
  sit next to each other as a plausible story rather than a demonstrated
  one.
  """
  code = resolve_action_code(_driver_snip(), canonical_layer="description")
  with pytest.raises(Exception) as excinfo:
    exec_python(code, {}, None, snippet_id=NESTED_ID)
  assert "Empty or missing Python code for 'authoring/random_note'" in str(excinfo.value)


def test_python_routing_layer_is_still_honoured():
  """NON-VACUITY for the client fix.

  `engineRoutingLayer` keeps forwarding 'python'. If the engine stopped
  honouring it, the plugin's python-canonical branch would start parsing
  Recipes it must not parse — so the client fix's decision to forward
  this one is only safe while this holds.
  """
  code = resolve_action_code(_driver_snip(), canonical_layer="python")
  assert code is not None
  assert "return 41" in code


def test_second_pass_with_resolutions_transpiles_and_runs():
  """The round trip completes: slot miss -> resolutions -> real code.

  Mirrors the plugin's second pass, which supplies `slot_resolutions`
  and no routing layer.
  """
  key = compute_slot_cache_key("a random float between 0 and 1", NESTED_ID)
  code = resolve_action_code(
    _driver_snip(), slot_resolutions={key: "__import__('random').random()"}
  )
  assert code is not None and code.strip()
  assert "<unresolved slot" not in code

  stdout, result = exec_python(
    code, {"scale": 1.0}, None, snippet_id=NESTED_ID, declared_inputs=["scale"]
  )
  assert isinstance(result, float)
  assert 0.0 <= result <= 2.0


def test_the_cached_thing_is_the_expression_not_the_value():
  """Driver policy, executable rather than asserted in prose.

  The same cached `python_expr` re-executes every run, so two runs of
  one cache entry must be able to differ. A cache that served VALUES
  would make this loop return one number forever.
  """
  key = compute_slot_cache_key("a random float between 0 and 1", NESTED_ID)
  code = resolve_action_code(
    _driver_snip(), slot_resolutions={key: "__import__('random').random()"}
  )
  seen = set()
  for _ in range(40):
    _, result = exec_python(
      code, {"scale": 1.0}, None, snippet_id=NESTED_ID, declared_inputs=["scale"]
    )
    seen.add(result)
  assert len(seen) > 1, "re-executing the cached expression produced one value"
