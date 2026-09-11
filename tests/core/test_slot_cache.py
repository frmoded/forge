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
# CW 1200 — parse_slots_section reads frontmatter's `slots_cache` too,
# falling back to the body # Slots section only when frontmatter has
# none (read-compat, not a hard cutover — at least one note on disk,
# forge-tutorial/09-slots/octopus_fact.md, still has a real body
# section as of this drain).
# ---------------------------------------------------------------------


def test_parse_slots_section_reads_frontmatter_slots_cache():
  fm = {"slots_cache": {"abc123": "42"}}
  assert parse_slots_section("", fm) == {"abc123": "42"}


def test_parse_slots_section_frontmatter_absent_falls_back_to_body():
  body = (
    "# Slots\n\n"
    "```yaml\n"
    "slots:\n"
    '  "k1": "v1"\n'
    "```\n"
  )
  # No frontmatter arg at all (default None) — matches every pre-
  # migration caller that hasn't been updated to pass one yet.
  assert parse_slots_section(body) == {"k1": "v1"}
  # Explicit None, and a dict with no slots_cache key — both "absent".
  assert parse_slots_section(body, None) == {"k1": "v1"}
  assert parse_slots_section(body, {"type": "action"}) == {"k1": "v1"}


def test_parse_slots_section_merges_body_and_frontmatter_no_false_miss():
  # THE MIGRATION-SAFETY PROPERTY. A note mid-migration can have keys
  # in EITHER place — a false cache miss (re-hitting the LLM for
  # something already resolved) is exactly what read-compat exists to
  # prevent. Frontmatter wins on key collision since it's the newer
  # source of truth going forward.
  body = (
    "# Slots\n\n"
    "```yaml\n"
    "slots:\n"
    '  "body_only": "1"\n'
    '  "both": "STALE_BODY_VALUE"\n'
    "```\n"
  )
  fm = {"slots_cache": {"fm_only": "2", "both": "FRESH_FM_VALUE"}}
  result = parse_slots_section(body, fm)
  assert result == {
    "body_only": "1",
    "fm_only": "2",
    "both": "FRESH_FM_VALUE",
  }


def test_parse_slots_section_frontmatter_slots_cache_wrong_shape_falls_back():
  # Defensive: a malformed slots_cache (not a dict) is treated the same
  # as absent, not a crash — matches the tolerant-by-design contract
  # the rest of this module already follows.
  body = "# Slots\n\n```yaml\nslots:\n  \"k1\": \"v1\"\n```\n"
  assert parse_slots_section(body, {"slots_cache": "not a dict"}) == {"k1": "v1"}
  assert parse_slots_section(body, {"slots_cache": ["a", "list"]}) == {"k1": "v1"}


def test_parse_slots_section_frontmatter_slots_cache_drops_non_string_values():
  # Same filter the body-parsing path already applies.
  fm = {"slots_cache": {"real_key": "valid", "int_value": 42, "list_value": [1, 2]}}
  assert parse_slots_section("", fm) == {"real_key": "valid"}


# ---------------------------------------------------------------------
# serialize_slots_section
#
# CW 1200 — no longer renders a body `# Slots` heading + fenced YAML
# string. Returns a plain dict (sorted by key) ready to be written as
# the value of a note's `slots_cache` frontmatter field by whatever
# frontmatter-writing tool the caller uses — that tool owns YAML
# emission (and therefore string escaping) for the surrounding
# frontmatter block as a whole, so this function no longer needs its
# own manual backslash/quote-escaping logic at all. Returns {} for an
# empty input dict — callers omit the `slots_cache` field entirely
# when there's nothing to cache, same omit-when-empty convention the
# old body-heading version used.
# ---------------------------------------------------------------------


def test_serialize_slots_section_empty_dict_returns_empty_dict():
  assert serialize_slots_section({}) == {}


def test_serialize_slots_section_returns_a_plain_dict():
  rendered = serialize_slots_section({"k1": "42"})
  assert rendered == {"k1": "42"}
  assert isinstance(rendered, dict)


def test_serialize_slots_section_stable_ordering_by_key():
  # Insertion order should NOT determine output order — only
  # asciibetical-by-key. Critical for diff-friendliness (a YAML dumper
  # downstream preserves dict insertion order, so this is what actually
  # controls the emitted line order).
  d1 = {"zzz": "v1", "aaa": "v2", "mmm": "v3"}
  d2 = {"mmm": "v3", "aaa": "v2", "zzz": "v1"}
  out1 = serialize_slots_section(d1)
  out2 = serialize_slots_section(d2)
  assert list(out1.keys()) == list(out2.keys()) == ["aaa", "mmm", "zzz"]
  assert out1 == out2 == d1


def test_serialize_slots_section_values_pass_through_unescaped():
  # No manual escaping any more — a native dict has no string-embedding
  # concerns. Special characters in a value are just the value.
  d = {'key"with"quotes': 'val\\with\\back', "k2": 'expr("nested")'}
  rendered = serialize_slots_section(d)
  assert rendered == d


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
  reparsed = parse_slots_section("", {"slots_cache": rendered})
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
  reparsed = parse_slots_section("", {"slots_cache": rendered})
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
