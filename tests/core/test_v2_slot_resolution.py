"""V2.1 Phase 2 — end-to-end slot resolution through the executor.

Phase 1 (v0.2.181) shipped the parser + transpiler hooks. Phase 2
wires them into the executor's V2 transpile path so:

- A V2 note with `{{...}}` slots triggers SlotCacheMissError on first
  Forge-click (plugin then POSTs to /resolve-slot, writes the
  resolutions to frontmatter, second click hits cache).
- A V2 note with cache-hit slots transpiles cleanly.
- A V2 note with NO slots transpiles unchanged (regression).
"""

import pytest

from forge.core.executor import resolve_action_code
from forge.core.slot_cache import SlotCacheMissError


def _make_v2_snippet(emm_body: str, snippet_id: str = "test/note"):
  """Build the snippet dict shape resolve_action_code consumes for V2."""
  body = (
    "---\n"
    "type: action\n"
    "---\n"
    "\n"
    "# Description\n"
    "\n"
    "Test note.\n"
    "\n"
    "# E--\n"
    "\n"
    f"{emm_body}\n"
  )
  return {
    "snippet_id": snippet_id,
    "body": body,
    "meta": {"type": "action"},
  }


def test_v2_slot_cache_miss_raises():
  """Pristine V2 note with a slot, no slot_resolutions cache → miss."""
  snip = _make_v2_snippet(
    'Let x = {{a random fun fact about octopuses}}.\nReturn x.'
  )
  with pytest.raises(SlotCacheMissError) as exc_info:
    resolve_action_code(snip)
  err = exc_info.value
  assert len(err.missing) == 1
  miss = err.missing[0]
  assert miss["slot_text"] == "a random fun fact about octopuses"
  assert miss["snippet_id"] == "test/note"
  # surrounding_context default empty (per v0.2.70 cache-key contract)
  assert miss["surrounding_context"] == ""


def test_v2_slot_cache_hit_substitutes():
  """V2 note + slot_resolutions cache hit → expression substituted."""
  from forge.core.slot_cache import compute_slot_cache_key
  snip = _make_v2_snippet(
    'Let x = {{octopus fact}}.\nReturn x.'
  )
  key = compute_slot_cache_key("octopus fact", "test/note")
  resolutions = {key: '"Octopuses have three hearts."'}
  code = resolve_action_code(snip, slot_resolutions=resolutions)
  assert code is not None
  assert '"Octopuses have three hearts."' in code
  assert "def compute" in code


def test_v2_no_slots_unchanged_path():
  """V2 note with no slots → transpiles cleanly, no SlotCacheMissError."""
  snip = _make_v2_snippet('Return 42.')
  code = resolve_action_code(snip)
  assert code is not None
  assert "return 42" in code


def test_v2_multiple_slots_batched_in_one_miss():
  """Multiple slots in one note all surface in a single
  SlotCacheMissError (single-pass collection per v0.2.70 delta #2)."""
  snip = _make_v2_snippet(
    'Let a = {{first slot}}.\nLet b = {{second slot}}.\nReturn a.'
  )
  with pytest.raises(SlotCacheMissError) as exc_info:
    resolve_action_code(snip)
  texts = sorted(m["slot_text"] for m in exc_info.value.missing)
  assert texts == ["first slot", "second slot"]


def test_v2_cache_key_is_slot_text_plus_snippet_id():
  """Cache invalidation contract: same slot_text in same snippet
  shares a key. Different snippet IDs (even with same text) get
  different keys."""
  from forge.core.slot_cache import compute_slot_cache_key
  key_a = compute_slot_cache_key("a fact", "note/one")
  key_a_again = compute_slot_cache_key("a fact", "note/one")
  key_b = compute_slot_cache_key("a fact", "note/two")
  key_c = compute_slot_cache_key("different text", "note/one")
  assert key_a == key_a_again
  assert key_a != key_b
  assert key_a != key_c


def test_v2_slot_inside_chip_call_kwarg():
  """Slot in expression position (chip-call kwarg) is collected the
  same as a top-level Let RHS."""
  snip = _make_v2_snippet(
    'Call [[print]] with text={{a haiku title in 3 words}}.\nReturn.'
  )
  with pytest.raises(SlotCacheMissError) as exc_info:
    resolve_action_code(snip)
  assert len(exc_info.value.missing) == 1
  assert exc_info.value.missing[0]["slot_text"] == "a haiku title in 3 words"


def test_v2_slot_inside_arithmetic_binop():
  """Slot inside an arithmetic expression resolves cleanly (numeric
  result spliced into the binop)."""
  from forge.core.slot_cache import compute_slot_cache_key
  snip = _make_v2_snippet(
    'Let count = {{the number of strings on a guitar}} + 1.\n'
    'Return count.'
  )
  key = compute_slot_cache_key("the number of strings on a guitar", "test/note")
  code = resolve_action_code(snip, slot_resolutions={key: "6"})
  assert "(6 + 1)" in code
