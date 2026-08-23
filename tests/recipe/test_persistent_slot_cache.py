"""Drain 2026-08-24-2350 — the `# Slots` sidecar, finally wired.

WHAT WAS WRONG. `slot_cache.py` has shipped `parse_slots_section` /
`serialize_slots_section` since v0.2.70 under a docstring reading "NOT
YET WIRED. Phase 2 will call parse_slots_section from the canonical
compile path". Phase 2 never happened. FEEDBACK 2330 §4 found the two
helpers referenced by nothing but their own tests, and the plugin
STRIPPING the heading rather than writing it — so every run of a
slot-bearing note re-hit the LLM.

The driver's ruling is explicit: cache slots, Recipe -> Python and
Description -> Recipe; never execution results. This wires the first of
those.

THE LOAD-BEARING PROPERTY, and the reason a cache is allowed here at
all: what is stored is the EXPRESSION, not the value. A cache hit
returns `__import__('random').random()`, which re-executes on every
run. `test_a_hit_still_produces_a_fresh_value_every_run` is the one to
look at if anyone ever wonders whether this cache violates the policy.

Nested ids throughout: the cache key is (slot_text, snippet_id), so a
bare-id test would exercise different keys than the driver's note.
"""

import pytest

from forge.core.executor import exec_python, resolve_action_code
from forge.core.slot_cache import (
  SlotCacheMissError,
  compute_slot_cache_key,
  serialize_slots_section,
)

NESTED_ID = "authoring/random_note"
SLOT_TEXT = "a random float between 0 and 1"
EXPR = "__import__('random').random()"

_HEAD = """---
type: action
source_facet: description
---

# Description

A random number between 0 and 2, multiplied by an input scale.

# Recipe

Input scale: float = 1.0.
Let raw = {{ %s }}.
Let scaled = raw * 2.
Let result = scaled * scale.
Return result.

# Python

def compute(context):
    return 41
"""


def _body(slot_text=SLOT_TEXT, slots=None):
  body = _HEAD % slot_text
  if slots is not None:
    body += "\n" + serialize_slots_section(slots)
  return body


def _snip(**kw):
  return {
    "snippet_id": NESTED_ID,
    "body": _body(**kw),
    "meta": {"type": "action", "source_facet": "description"},
  }


def _cached_body(slot_text=SLOT_TEXT):
  return _body(
    slot_text=slot_text,
    slots={compute_slot_cache_key(slot_text, NESTED_ID): EXPR},
  )


# --- the cache is consulted -----------------------------------------

def test_no_slots_section_still_raises_the_miss():
  """The miss path is untouched — it is how entries get created."""
  with pytest.raises(SlotCacheMissError):
    resolve_action_code(_snip())


def test_a_persisted_slots_section_is_a_clean_hit():
  """THE ACCEPTANCE, engine half.

  No SlotCacheMissError means no 409, which means the plugin never
  calls /resolve-slot. That is the zero-LLM-calls assertion stated as
  a property of the code path rather than as a stopwatch reading.
  """
  code = resolve_action_code(
    {"snippet_id": NESTED_ID, "body": _cached_body(),
     "meta": {"type": "action", "source_facet": "description"}},
  )
  assert code is not None
  assert EXPR in code
  assert "<unresolved slot" not in code


def test_a_hit_still_produces_a_fresh_value_every_run():
  """THE POLICY, executable.

  The cached thing is an expression. If this ever returns one value,
  the cache has started serving results and the driver's rule is
  broken.
  """
  code = resolve_action_code(
    {"snippet_id": NESTED_ID, "body": _cached_body(),
     "meta": {"type": "action", "source_facet": "description"}},
  )
  seen = set()
  for _ in range(40):
    _, result = exec_python(
      code, {"scale": 1.0}, None, snippet_id=NESTED_ID,
      declared_inputs=["scale"],
    )
    seen.add(result)
  assert len(seen) > 1


def test_editing_the_slot_prose_invalidates_the_entry():
  """Natural invalidation: the key includes the slot text.

  The persisted entry is keyed to the OLD prose, so the new prose
  misses and re-resolves. No explicit invalidation step exists or is
  needed.
  """
  stale = _body(
    slot_text="a random float between 0 and 100",
    slots={compute_slot_cache_key(SLOT_TEXT, NESTED_ID): EXPR},
  )
  with pytest.raises(SlotCacheMissError) as excinfo:
    resolve_action_code(
      {"snippet_id": NESTED_ID, "body": stale,
       "meta": {"type": "action", "source_facet": "description"}},
    )
  assert "a random float between 0 and 100" in str(excinfo.value)


def test_an_entry_keyed_to_another_snippet_does_not_leak():
  """The id half of the key is load-bearing too.

  Two notes can hold the same slot prose and mean different things;
  a bare-basename key would let one note's resolution answer the
  other's slot.
  """
  foreign = _body(slots={compute_slot_cache_key(SLOT_TEXT, "other/note"): EXPR})
  with pytest.raises(SlotCacheMissError):
    resolve_action_code(
      {"snippet_id": NESTED_ID, "body": foreign,
       "meta": {"type": "action", "source_facet": "description"}},
    )


def test_inline_resolutions_win_over_a_persisted_entry():
  """The miss path must be able to correct a bad persisted entry.

  `slot_resolutions` is what the plugin passes on its second pass. If
  a persisted entry shadowed it, a note with a broken cached
  expression could never be repaired by re-resolving.
  """
  body = _body(slots={compute_slot_cache_key(SLOT_TEXT, NESTED_ID): "'STALE'"})
  code = resolve_action_code(
    {"snippet_id": NESTED_ID, "body": body,
     "meta": {"type": "action", "source_facet": "description"}},
    slot_resolutions={compute_slot_cache_key(SLOT_TEXT, NESTED_ID): EXPR},
  )
  assert EXPR in code
  assert "STALE" not in code


def test_a_malformed_slots_section_degrades_to_a_miss():
  """Tolerance, end to end.

  `parse_slots_section` returns {} on garbage. What matters is that
  the caller then behaves like a cold cache — re-resolve — rather than
  crashing a run on a hand-mangled heading.
  """
  body = _HEAD % SLOT_TEXT + "\n# Slots\n\n```yaml\n: : not yaml : :\n```\n"
  with pytest.raises(SlotCacheMissError):
    resolve_action_code(
      {"snippet_id": NESTED_ID, "body": body,
       "meta": {"type": "action", "source_facet": "description"}},
    )


# --- §2: the retired routing branch ---------------------------------

def test_description_routing_layer_no_longer_suppresses_the_recipe():
  """Drain 2350 §2 — the branch is gone.

  It was unreachable from its documented caller (transitive
  `context.compute` passes no layer at all) and inverted on the only
  path that ever reached it: the two-hop auto-forge derives the Recipe
  FROM the Description immediately before running, so the Recipe is
  the freshest thing on the note.

  Replaces drain 2330's `test_description_routing_layer_still_returns_none`,
  which recorded the old behaviour and was labelled for deletion at
  exactly this retirement.
  """
  code = resolve_action_code(
    {"snippet_id": NESTED_ID, "body": _cached_body(),
     "meta": {"type": "action", "source_facet": "description"}},
    canonical_layer="description",
  )
  assert code is not None, "the 'description' -> None branch is back"
  assert EXPR in code


def test_python_routing_layer_is_still_honoured():
  """NON-VACUITY. `engineRoutingLayer` still forwards 'python', and the
  plugin's python-canonical branch depends on this short-circuit
  skipping a Recipe it must not parse."""
  code = resolve_action_code(
    {"snippet_id": NESTED_ID, "body": _cached_body(),
     "meta": {"type": "action", "source_facet": "description"}},
    canonical_layer="python",
  )
  assert "return 41" in code
