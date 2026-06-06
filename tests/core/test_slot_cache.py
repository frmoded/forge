"""Pure-core tests for forge.core.slot_cache.

Phase 1 §1.3 — new-feature shape (NOT failing-first per
cc-prompt-queue.md §120-129). Coverage target: every observable
behavior in the helper spec.

These helpers ship UNWIRED. Phase 2 connects them to the canonical
compile path at executor.py:486-505. Suite-level coverage now means
Phase 2 can wire with confidence.
"""

import pytest

from forge.core.slot_cache import (
    compute_slot_cache_key,
    parse_slots_section,
    serialize_slots_section,
)


# ---------------------------------------------------------------------
# parse_slots_section
# ---------------------------------------------------------------------


def test_parse_slots_section_no_heading_returns_empty():
  body = (
    "# English\n\nDo print(\"hello\").\n\n"
    "# Python\n\n```python\ndef compute(context):\n    print(\"hello\")\n```\n"
  )
  assert parse_slots_section(body) == {}


def test_parse_slots_section_valid_yaml_heading_parses():
  body = (
    "# English\n\n"
    "Set x to {{the answer}}.\n\n"
    "# Slots\n\n"
    "```yaml\n"
    "slots:\n"
    '  "abc123": "42"\n'
    '  "def456": "\\"red\\""\n'
    "```\n"
  )
  result = parse_slots_section(body)
  assert result == {"abc123": "42", "def456": '"red"'}


def test_parse_slots_section_malformed_yaml_returns_empty():
  body = (
    "# Slots\n\n"
    "```yaml\n"
    "slots:\n"
    "  this is: { not valid YAML at all }: : :\n"
    "  another bad line: ]]]]] [[[[ ]\n"
    "```\n"
  )
  # Helper swallows yaml.YAMLError and returns {} per tolerance shape.
  assert parse_slots_section(body) == {}


def test_parse_slots_section_empty_heading_returns_empty():
  body = "# English\n\nplain text.\n\n# Slots\n\n"
  assert parse_slots_section(body) == {}


def test_parse_slots_section_accepts_flat_dict_without_slots_wrapper():
  # Forward-compat: an older or hand-edited cache without the
  # `slots:` wrapper still parses as long as the top level is dict
  # str → str.
  body = (
    "# Slots\n\n"
    "```yaml\n"
    '"key1": "value1"\n'
    '"key2": "value2"\n'
    "```\n"
  )
  assert parse_slots_section(body) == {"key1": "value1", "key2": "value2"}


def test_parse_slots_section_drops_non_string_values():
  # Defensive: a malformed cache might have non-string values; helper
  # filters them out rather than returning a mixed-type dict.
  body = (
    "# Slots\n\n"
    "```yaml\n"
    "slots:\n"
    '  "real_key": "valid"\n'
    '  "int_value": 42\n'
    '  "list_value": [1, 2, 3]\n'
    "```\n"
  )
  assert parse_slots_section(body) == {"real_key": "valid"}


def test_parse_slots_section_stops_at_next_heading():
  body = (
    "# Slots\n\n"
    "```yaml\n"
    "slots:\n"
    '  "k1": "v1"\n'
    "```\n\n"
    "# Dependencies\n\n[[other]]\n"
  )
  assert parse_slots_section(body) == {"k1": "v1"}


def test_parse_slots_section_handles_empty_body():
  assert parse_slots_section("") == {}
  assert parse_slots_section(None) == {}


# ---------------------------------------------------------------------
# serialize_slots_section
# ---------------------------------------------------------------------


def test_serialize_slots_section_empty_dict_returns_empty_string():
  assert serialize_slots_section({}) == ""


def test_serialize_slots_section_single_entry_renders_full_heading():
  rendered = serialize_slots_section({"k1": "42"})
  assert "# Slots" in rendered
  assert "```yaml" in rendered
  assert "slots:" in rendered
  assert '"k1": "42"' in rendered
  assert "```" in rendered


def test_serialize_slots_section_stable_ordering_by_key():
  # Insertion order should NOT determine output order — only
  # asciibetical-by-key. Critical for diff-friendliness.
  d1 = {"zzz": "v1", "aaa": "v2", "mmm": "v3"}
  d2 = {"mmm": "v3", "aaa": "v2", "zzz": "v1"}
  out1 = serialize_slots_section(d1)
  out2 = serialize_slots_section(d2)
  assert out1 == out2
  # Confirm the actual sorted order:
  aaa_pos = out1.index("aaa")
  mmm_pos = out1.index("mmm")
  zzz_pos = out1.index("zzz")
  assert aaa_pos < mmm_pos < zzz_pos


def test_serialize_slots_section_escapes_backslash_and_quote():
  d = {'key"with"quotes': 'val\\with\\back', "k2": 'expr("nested")'}
  rendered = serialize_slots_section(d)
  # Backslashes doubled, quotes escaped.
  assert '"key\\"with\\"quotes"' in rendered
  assert '"val\\\\with\\\\back"' in rendered
  assert '"expr(\\"nested\\")"' in rendered


# ---------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------


def test_parse_serialize_parse_roundtrip_preserves_dict():
  original = {
    "abc123": "42",
    "def456": '"red"',
    "ghi789": "[1, 2, 3]",
  }
  rendered = serialize_slots_section(original)
  reparsed = parse_slots_section(rendered)
  assert reparsed == original


def test_parse_serialize_parse_roundtrip_handles_python_expressions():
  # Real-world Python expressions a resolver might return.
  original = {
    "k_int": "7",
    "k_str": '"hello world"',
    "k_list": "[1901, 1907, 1913]",
    "k_dict": '{"color": "blue", "size": 5}',
    "k_call": "range(10)",
  }
  rendered = serialize_slots_section(original)
  reparsed = parse_slots_section(rendered)
  assert reparsed == original


# ---------------------------------------------------------------------
# compute_slot_cache_key
# ---------------------------------------------------------------------


def test_compute_slot_cache_key_deterministic_same_input_same_output():
  k1 = compute_slot_cache_key("text", "snippet", "context")
  k2 = compute_slot_cache_key("text", "snippet", "context")
  assert k1 == k2
  # And specifically: 64 hex chars (sha256).
  assert len(k1) == 64
  assert all(c in "0123456789abcdef" for c in k1)


def test_compute_slot_cache_key_distinguishes_slot_text():
  k1 = compute_slot_cache_key("text_a", "snippet", "context")
  k2 = compute_slot_cache_key("text_b", "snippet", "context")
  assert k1 != k2


def test_compute_slot_cache_key_distinguishes_snippet_id():
  k1 = compute_slot_cache_key("text", "snippet_a", "context")
  k2 = compute_slot_cache_key("text", "snippet_b", "context")
  assert k1 != k2


def test_compute_slot_cache_key_distinguishes_surrounding_context():
  k1 = compute_slot_cache_key("text", "snippet", "context_a")
  k2 = compute_slot_cache_key("text", "snippet", "context_b")
  assert k1 != k2


def test_compute_slot_cache_key_no_concatenation_collision():
  # snippet_id "ab" + slot_text "c" must NOT collide with snippet_id
  # "a" + slot_text "bc". The null-byte separator in the helper
  # implementation handles this.
  k1 = compute_slot_cache_key("c", "ab", "")
  k2 = compute_slot_cache_key("bc", "a", "")
  assert k1 != k2


def test_compute_slot_cache_key_none_context_equivalent_to_empty():
  # API affordance: None and "" mean the same thing.
  k_none = compute_slot_cache_key("text", "snippet", None)
  k_empty = compute_slot_cache_key("text", "snippet", "")
  assert k_none == k_empty


def test_compute_slot_cache_key_rejects_non_string_input():
  with pytest.raises(TypeError):
    compute_slot_cache_key(123, "snippet")  # int slot_text
  with pytest.raises(TypeError):
    compute_slot_cache_key("text", 456)  # int snippet_id
  with pytest.raises(TypeError):
    compute_slot_cache_key("text", "snippet", 789)  # int context


def test_compute_slot_cache_key_handles_unicode():
  # E-- canonical English may contain non-ASCII (em-dashes, smart
  # quotes from copy-paste). UTF-8 encoding before hashing handles
  # this; same Unicode in = same hex out.
  k1 = compute_slot_cache_key("a calm blue — pale", "snippet", "")
  k2 = compute_slot_cache_key("a calm blue — pale", "snippet", "")
  assert k1 == k2


def test_compute_slot_cache_key_noop_idempotent():
  # Sanity check the helper has no global state — calling it 1000
  # times with the same input doesn't drift.
  base = compute_slot_cache_key("text", "snippet", "context")
  for _ in range(100):
    assert compute_slot_cache_key("text", "snippet", "context") == base
