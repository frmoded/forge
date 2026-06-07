"""Engine-side slot resolution + B7.3 unified-cache integration tests.

v0.2.72 — `# Python` IS the cache (B7.3 unification). The separate
`# Slots` heading from v0.2.70/v0.2.71 is dead; the engine ignores it.

These tests exercise the unified contract:

  - First-pass cache miss: no `# Python`, no slot_resolutions →
    SlotCacheMissError with all unresolved slots.
  - Second-pass populate: slot_resolutions dict supplied → resolver
    looks up every slot, returns full Python.
  - Cache hit: `# Python` present + english_hash matches → return
    cached Python without transpile.
  - Cache invalidation: `# Python` present + english_hash mismatches
    → fall through to transpile (which may re-raise on slots).
  - edit_mode override: `edit_mode: python` → use `# Python`
    unconditionally (skip hash check).
  - Slot-free regression: existing canonical snippets with no slots
    work unchanged.
"""
import pytest

from forge.core.executor import resolve_action_code
from forge.core.slot_cache import (
  SlotCacheMissError,
  compute_english_hash,
  compute_slot_cache_key,
)


def _canonical_snippet(
  english,
  python_code=None,
  english_hash=None,
  edit_mode=None,
  snippet_id="forge-moda/slot_demo",
):
  """Build a canonical-form snippet, optionally with a # Python facet
  and english_hash + edit_mode frontmatter fields."""
  body = f"# English\n\n{english}\n"
  if python_code is not None:
    body += f"\n# Python\n\n```python\n{python_code}\n```\n"
  meta = {"type": "action", "facet_form": "canonical", "inputs": []}
  if english_hash is not None:
    meta["english_hash"] = english_hash
  if edit_mode is not None:
    meta["edit_mode"] = edit_mode
  return {
    "snippet_id": snippet_id,
    "meta": meta,
    "body": body,
  }


# --- 1. Cache miss: no Python, no slot_resolutions ---------------------


def test_no_python_no_resolutions_surfaces_all_missing_in_order():
  snip = _canonical_snippet(
    "Set greeting to {{a friendly hello message}}.\n"
    "Set color to {{a calm blue}}.\n"
    "Do [[print]](greeting)."
  )
  with pytest.raises(SlotCacheMissError) as exc:
    resolve_action_code(snip)
  missing = exc.value.missing
  assert len(missing) == 2
  assert missing[0]["slot_text"] == "a friendly hello message"
  assert missing[1]["slot_text"] == "a calm blue"
  for entry in missing:
    assert entry["snippet_id"] == "forge-moda/slot_demo"


# --- 2. Slot-free canonical (regression) ----------------------------


def test_slot_free_canonical_no_python_returns_transpiled():
  snip = _canonical_snippet(
    'Do [[print]]("plain canonical, no slots").'
  )
  code = resolve_action_code(snip)
  assert isinstance(code, str)
  assert "def compute(context):" in code
  assert '"plain canonical, no slots"' in code


# --- 3. Second pass: slot_resolutions supplied ----------------------


def test_slot_resolutions_supplied_returns_transpiled_python():
  english = (
    'Set greeting to {{a friendly hello}}.\n'
    'Do [[print]](greeting).'
  )
  snippet_id = "forge-moda/slot_demo"
  snip = _canonical_snippet(english, snippet_id=snippet_id)
  # Pre-compute the cache key for the slot the resolver will request.
  k = compute_slot_cache_key("a friendly hello", snippet_id)
  resolutions = {k: '"Hello, dear reader!"'}
  code = resolve_action_code(snip, slot_resolutions=resolutions)
  assert isinstance(code, str)
  assert "def compute(context):" in code
  assert '"Hello, dear reader!"' in code


def test_slot_resolutions_partial_still_surfaces_remaining_missing():
  english = (
    'Set greeting to {{a friendly hello}}.\n'
    'Set color to {{a calm blue}}.\n'
    'Do [[print]](greeting).'
  )
  snippet_id = "forge-moda/slot_demo"
  snip = _canonical_snippet(english, snippet_id=snippet_id)
  # Only resolve the greeting; color still missing.
  k = compute_slot_cache_key("a friendly hello", snippet_id)
  with pytest.raises(SlotCacheMissError) as exc:
    resolve_action_code(snip, slot_resolutions={k: '"Hello"'})
  missing = exc.value.missing
  assert len(missing) == 1
  assert missing[0]["slot_text"] == "a calm blue"


# --- 4. # Python + matching english_hash → cache hit -----------------


def test_python_present_matching_english_hash_returns_cached():
  english = (
    'Set greeting to {{a friendly hello}}.\n'
    'Do [[print]](greeting).'
  )
  # Pre-baked Python that simulates what a prior transpile produced.
  python = (
    'def compute(context):\n'
    '    greeting = "Hello, dear reader!"\n'
    '    print(greeting)'
  )
  # Hash the English exactly as the engine will (via the same helper).
  english_hash = compute_english_hash(english)
  snip = _canonical_snippet(
    english,
    python_code=python,
    english_hash=english_hash,
  )
  code = resolve_action_code(snip)
  assert code is not None
  assert "Hello, dear reader!" in code


# --- 5. # Python + mismatched english_hash → re-transpile ------------


def test_python_present_mismatched_english_hash_re_transpiles():
  # The English has been edited since # Python was last generated;
  # the cached hash no longer matches. Engine falls through to
  # transpile and surfaces SlotCacheMissError because slots are
  # unresolved.
  english = (
    'Set greeting to {{a NEW slot text}}.\n'
    'Do [[print]](greeting).'
  )
  stale_python = (
    'def compute(context):\n'
    '    greeting = "Hello, dear reader!"\n'
    '    print(greeting)'
  )
  stale_hash = compute_english_hash("DIFFERENT english")
  snip = _canonical_snippet(
    english,
    python_code=stale_python,
    english_hash=stale_hash,
  )
  with pytest.raises(SlotCacheMissError) as exc:
    resolve_action_code(snip)
  missing = exc.value.missing
  assert len(missing) == 1
  assert missing[0]["slot_text"] == "a NEW slot text"


# --- 6. edit_mode: python → use # Python unconditionally -------------


def test_edit_mode_python_uses_python_unconditionally():
  # No english_hash in frontmatter; in python mode the engine should
  # NOT compute one and NOT compare. Just use # Python as-is.
  english = "Set greeting to {{whatever}}."  # would normally miss
  python = (
    'def compute(context):\n'
    '    print("manual override")'
  )
  snip = _canonical_snippet(
    english,
    python_code=python,
    edit_mode="python",
    # NO english_hash set — proves python mode skips the check.
  )
  code = resolve_action_code(snip)
  assert "manual override" in code


def test_edit_mode_python_skips_hash_check_even_with_mismatch():
  # If english_hash IS set and mismatches, python mode still wins.
  english = "Set greeting to {{whatever}}."
  python = (
    'def compute(context):\n'
    '    print("manual override")'
  )
  snip = _canonical_snippet(
    english,
    python_code=python,
    english_hash="0" * 64,  # definitely doesn't match
    edit_mode="python",
  )
  code = resolve_action_code(snip)
  assert "manual override" in code


# --- 7. Legacy free-English regression --------------------------------


def test_legacy_free_english_snippet_with_python_unchanged():
  # No facet_form; engine returns # Python directly.
  body = (
    "# English\n\n"
    "Print hello world.\n\n"
    "# Python\n\n"
    "```python\n"
    "def compute(context):\n"
    "    print('hello world')\n"
    "```\n"
  )
  snip = {
    "snippet_id": "legacy/demo",
    "meta": {"type": "action", "inputs": []},
    "body": body,
  }
  code = resolve_action_code(snip)
  assert code is not None
  assert "hello world" in code


# --- 8. Legacy: no Python, no canonical opt-in → None ----------------


def test_legacy_no_python_no_canonical_returns_none():
  body = "# English\n\nSome free-english text without code.\n"
  snip = {
    "snippet_id": "legacy/no_python",
    "meta": {"type": "action", "inputs": []},
    "body": body,
  }
  code = resolve_action_code(snip)
  assert code is None


# --- 9. End-to-end miss → second pass → cached hit ------------------


def test_unified_cache_miss_then_populate_then_hit_e2e():
  """v0.2.72 B7.3 freeze-by-cache contract using # Python:

  1. First pass: no Python, no resolutions → SlotCacheMissError.
  2. Plugin calls /resolve-slot, gets resolutions.
  3. Engine second pass with slot_resolutions → returns transpiled
     Python with resolutions spliced in.
  4. Plugin writes # Python + english_hash back to disk.
  5. Third pass: # Python + matching english_hash → cache hit, no
     transpile, deterministic.
  """
  english = (
    'Set greeting to {{a friendly storybook hello}}.\n'
    'Do [[print]](greeting).'
  )
  snippet_id = "forge-moda/cache_e2e"

  # 1. First pass: miss.
  snip1 = _canonical_snippet(english, snippet_id=snippet_id)
  with pytest.raises(SlotCacheMissError) as first:
    resolve_action_code(snip1)
  misses = first.value.missing
  assert len(misses) == 1
  miss = misses[0]
  assert miss["slot_text"] == "a friendly storybook hello"

  # 2. Plugin resolves via /resolve-slot.
  resolved_expr = '"Hello, dear reader!"'
  cache_key = compute_slot_cache_key(miss["slot_text"], miss["snippet_id"])
  resolutions = {cache_key: resolved_expr}

  # 3. Engine second pass: full Python.
  code = resolve_action_code(snip1, slot_resolutions=resolutions)
  assert resolved_expr in code

  # 4. Plugin writes # Python + english_hash to disk. Simulate the
  #    resulting snippet body.
  english_hash = compute_english_hash(english)
  snip2 = _canonical_snippet(
    english,
    python_code=code,
    english_hash=english_hash,
    snippet_id=snippet_id,
  )

  # 5. Third pass: cache hit, no transpile, deterministic.
  code2 = resolve_action_code(snip2)
  assert code2 == code

  # And a fourth call against the same cached snippet — also a hit.
  code3 = resolve_action_code(snip2)
  assert code2 == code3
