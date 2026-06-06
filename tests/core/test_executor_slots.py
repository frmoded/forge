"""v0.2.70 — engine-side slot resolution integration tests.

Phase 2 §1.2 — TDD failing-first for the resolver-wired
`resolve_action_code` path. Covers:

  1. Slot-bearing snippet, no cache → SlotCacheMissError with all
     unresolved slots collected (document order preserved).
  2. Slot-bearing snippet, partial cache → only unresolved surface.
  3. Slot-bearing snippet, full cache → transpiles to Python normally.
  4. Slot-free canonical snippet → works unchanged (no regression).
  5. Slot-bearing snippet, malformed # Slots heading → tolerant:
     treats as no cache, surfaces all slots as missing.
  6. Cache-miss-then-cache-hit E2E (§1.6 contract): first transpile
     records misses; populating the cache and re-running transpiles
     cleanly with ZERO additional misses.

The engine resolver raises `SlotCacheMissError` on a miss. The error
carries a `missing` list of (slot_text, snippet_id) pairs which the
plugin batches into a single /resolve-slot call. After the plugin
writes the responses back to the snippet's # Slots heading and
re-fires the transpile gesture, the second pass is a clean cache hit.
"""

import pytest

from forge.core.executor import resolve_action_code
from forge.core.slot_cache import SlotCacheMissError, serialize_slots_section


def _slot_snippet(english, slots=None, snippet_id="forge-moda/slot_demo"):
  """Build a canonical-form snippet with optional # Slots heading."""
  body = f"# English\n\n{english}\n"
  if slots:
    body += "\n" + serialize_slots_section(slots) + "\n"
  return {
    "snippet_id": snippet_id,
    "meta": {"type": "action", "facet_form": "canonical", "inputs": []},
    "body": body,
  }


# --- 1. Slot-bearing, no cache ---------------------------------------


def test_slot_bearing_no_cache_raises_with_all_misses_in_order():
  snip = _slot_snippet(
    "Set greeting to {{a friendly hello message}}.\n"
    "Set color to {{a calm blue}}.\n"
    "Do [[print]](greeting)."
  )
  with pytest.raises(SlotCacheMissError) as exc:
    resolve_action_code(snip)
  missing = exc.value.missing
  assert len(missing) == 2
  # Document order preserved.
  assert missing[0]["slot_text"] == "a friendly hello message"
  assert missing[1]["slot_text"] == "a calm blue"
  # snippet_id threaded through to every missing entry.
  for entry in missing:
    assert entry["snippet_id"] == "forge-moda/slot_demo"


# --- 2. Slot-bearing, partial cache ----------------------------------


def test_slot_bearing_partial_cache_only_unresolved_surface():
  # Pre-populate only the second slot.
  from forge.core.slot_cache import compute_slot_cache_key
  k_color = compute_slot_cache_key("a calm blue", "forge-moda/slot_demo")
  snip = _slot_snippet(
    "Set greeting to {{a friendly hello message}}.\n"
    "Set color to {{a calm blue}}.\n"
    "Do [[print]](greeting).",
    slots={k_color: '"#3366cc"'},
  )
  with pytest.raises(SlotCacheMissError) as exc:
    resolve_action_code(snip)
  missing = exc.value.missing
  assert len(missing) == 1
  assert missing[0]["slot_text"] == "a friendly hello message"


# --- 3. Slot-bearing, full cache ------------------------------------


def test_slot_bearing_full_cache_returns_python():
  from forge.core.slot_cache import compute_slot_cache_key
  k_greet = compute_slot_cache_key(
    "a friendly hello message", "forge-moda/slot_demo")
  k_color = compute_slot_cache_key("a calm blue", "forge-moda/slot_demo")
  snip = _slot_snippet(
    'Set greeting to {{a friendly hello message}}.\n'
    'Set color to {{a calm blue}}.\n'
    'Do [[print]](greeting).',
    slots={
      k_greet: '"hello world"',
      k_color: '"#3366cc"',
    },
  )
  code = resolve_action_code(snip)
  assert isinstance(code, str)
  assert "def compute(context):" in code
  # The cached values should appear in the generated Python (the E--
  # emitter splices them verbatim).
  assert '"hello world"' in code
  # color isn't used in print but is assigned; should still appear.
  assert '"#3366cc"' in code


# --- 4. Slot-free canonical (regression) ----------------------------


def test_slot_free_canonical_unchanged():
  snip = _slot_snippet(
    'Do [[print]]("plain canonical, no slots").'
  )
  code = resolve_action_code(snip)
  assert isinstance(code, str)
  assert "def compute(context):" in code
  assert '"plain canonical, no slots"' in code


# --- 5. Slot-bearing, malformed # Slots heading ----------------------


def test_slot_bearing_malformed_cache_is_tolerant():
  # Body has a `# Slots` heading with broken YAML — parse_slots_section
  # returns {} per its tolerance contract. The engine treats this as
  # "no cache" and surfaces all slots as missing.
  body = (
    "# English\n\n"
    "Set x to {{the answer}}.\n\n"
    "# Slots\n\n"
    "```yaml\n"
    "this is: { ]]] absolutely [[ : not valid YAML\n"
    "```\n"
  )
  snip = {
    "snippet_id": "forge-moda/broken_demo",
    "meta": {"type": "action", "facet_form": "canonical", "inputs": []},
    "body": body,
  }
  with pytest.raises(SlotCacheMissError) as exc:
    resolve_action_code(snip)
  missing = exc.value.missing
  assert len(missing) == 1
  assert missing[0]["slot_text"] == "the answer"


# --- 6. §1.6: cache-miss-then-cache-hit E2E ------------------------


def test_cache_miss_then_cache_hit_e2e():
  """The load-bearing freeze-by-cache contract.

  First transpile of a slot-bearing snippet records the misses.
  The user/plugin populates the cache via the recorded keys.
  Second transpile runs to completion with ZERO additional misses.
  Two runs of the second transpile yield bytewise-identical Python
  (deterministic via cache).
  """
  from forge.core.slot_cache import compute_slot_cache_key

  english = (
    'Set greeting to {{a friendly storybook hello}}.\n'
    'Do [[print]](greeting).'
  )
  snippet_id = "forge-moda/cache_e2e"

  # First transpile: no cache → misses surface.
  snip1 = _slot_snippet(english, snippet_id=snippet_id)
  with pytest.raises(SlotCacheMissError) as first:
    resolve_action_code(snip1)
  misses = first.value.missing
  assert len(misses) == 1
  miss = misses[0]
  assert miss["slot_text"] == "a friendly storybook hello"
  assert miss["snippet_id"] == snippet_id

  # Simulate plugin: call /resolve-slot, get back python_expr,
  # populate the cache and rewrite the body.
  resolved_expr = '"Hello, dear reader!"'
  key = compute_slot_cache_key(miss["slot_text"], miss["snippet_id"])
  snip2 = _slot_snippet(
    english, slots={key: resolved_expr}, snippet_id=snippet_id,
  )

  # Second transpile: cache hit, no misses.
  code1 = resolve_action_code(snip2)
  assert isinstance(code1, str)
  assert resolved_expr in code1

  # Third transpile of the same cached snippet — deterministic.
  code2 = resolve_action_code(snip2)
  assert code1 == code2

  # AND a sanity check: a fourth call against the same snippet must
  # also be a cache hit, never re-raising.
  code3 = resolve_action_code(snip2)
  assert code1 == code3
