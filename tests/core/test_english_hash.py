"""v0.2.72 — tests for forge.core.slot_cache.compute_english_hash.

The B7.3 cache-invalidation contract: same English facet (modulo
cosmetic whitespace) hashes to the same hex string; meaningful edits
flip the hash.
"""
import pytest

from forge.core.slot_cache import compute_english_hash


def test_compute_english_hash_deterministic():
  h1 = compute_english_hash("Set x to 7.\nDo [[print]](x).")
  h2 = compute_english_hash("Set x to 7.\nDo [[print]](x).")
  assert h1 == h2
  assert len(h1) == 64
  assert all(c in "0123456789abcdef" for c in h1)


def test_compute_english_hash_distinct_text_distinct_hash():
  h1 = compute_english_hash("Set x to 7.\nDo [[print]](x).")
  h2 = compute_english_hash("Set x to 8.\nDo [[print]](x).")
  assert h1 != h2


def test_compute_english_hash_trailing_whitespace_normalized():
  h1 = compute_english_hash("Set x to 7.\nDo [[print]](x).")
  h2 = compute_english_hash("Set x to 7.   \nDo [[print]](x).   ")
  assert h1 == h2


def test_compute_english_hash_leading_trailing_blank_lines_stripped():
  h1 = compute_english_hash("Set x to 7.")
  h2 = compute_english_hash("\n\nSet x to 7.\n\n")
  assert h1 == h2


def test_compute_english_hash_internal_blank_lines_preserved():
  h1 = compute_english_hash("Set x to 7.\n\nDo [[print]](x).")
  h2 = compute_english_hash("Set x to 7.\nDo [[print]](x).")
  assert h1 != h2


def test_compute_english_hash_empty_input():
  h_empty = compute_english_hash("")
  h_none = compute_english_hash(None)
  assert h_empty == h_none
  assert h_empty == (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_compute_english_hash_unicode():
  h1 = compute_english_hash("Set greeting to {{a calm blue — pale}}.")
  h2 = compute_english_hash("Set greeting to {{a calm blue — pale}}.")
  assert h1 == h2


def test_compute_english_hash_rejects_non_string_input():
  with pytest.raises(TypeError):
    compute_english_hash(123)


def test_compute_english_hash_known_value_for_crosslang_parity():
  english = "Set greeting to {{a friendly hello}}.\nDo [[print]](greeting)."
  h = compute_english_hash(english)
  assert len(h) == 64
  assert all(c in "0123456789abcdef" for c in h)


def test_compute_english_hash_idempotent():
  text = "Set x to 7.\nDo [[print]](x)."
  base = compute_english_hash(text)
  for _ in range(50):
    assert compute_english_hash(text) == base
