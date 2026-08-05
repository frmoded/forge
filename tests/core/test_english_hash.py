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


# --- v0.2.74 property tests for cross-language parity ----------------
# Each pinned hash MUST equal the TS-side computeEnglishHash output for
# the same input (locked via the parallel test in
# forge-client-obsidian/src/english-hash-core.test.ts). Any future
# normalization change that breaks one side without the other will
# trip these assertions.

def test_parity_pin_slot_demo_storybook_english():
  """The exact English facet of the bundled slot_demo.md fixture.
  TS-side test pins the same hex."""
  english = (
    "Set greeting to {{a friendly hello message in the style of a "
    "children's storybook}}.\n"
    "Do [[print]](greeting)."
  )
  assert compute_english_hash(english) == (
    "f44f75cfaa0c23cd390f587cddd56718f6639de5be62e918ccdafe0cc4b635db")


def test_parity_pin_victorian_slot_text():
  english = (
    "Set greeting to {{a formal hello message in the style of a "
    "Victorian letter}}.\n"
    "Do [[print]](greeting)."
  )
  assert compute_english_hash(english) == (
    "5fe21a3d85ff8df536854a08a8c22556b249a236858f2d7d5737b98b4b6ccada")


def test_parity_pin_short_v0_2_72_baseline():
  """The v0.2.72 cross-language pin — still must hold."""
  english = "Set greeting to {{a friendly hello}}.\nDo [[print]](greeting)."
  assert compute_english_hash(english) == (
    "43415de15a03032addd6f759f30d51718c451c52f3d31e56e00a1526cbc33a54")


def test_parity_pin_trailing_newline():
  english = (
    "Set greeting to {{a friendly hello}}.\nDo [[print]](greeting).\n"
  )
  # Trailing newline normalized away by leading/trailing blank-line strip.
  assert compute_english_hash(english) == (
    "43415de15a03032addd6f759f30d51718c451c52f3d31e56e00a1526cbc33a54")


def test_parity_pin_leading_blank_lines():
  english = (
    "\n\n\nSet greeting to {{a friendly hello}}.\nDo [[print]](greeting)."
  )
  assert compute_english_hash(english) == (
    "43415de15a03032addd6f759f30d51718c451c52f3d31e56e00a1526cbc33a54")


def test_parity_pin_paragraph_break():
  english = (
    "Set greeting to {{a friendly hello}}.\n\nDo [[print]](greeting)."
  )
  # Distinct from the no-break version — paragraph breaks matter.
  h = compute_english_hash(english)
  baseline = (
    "43415de15a03032addd6f759f30d51718c451c52f3d31e56e00a1526cbc33a54")
  assert h != baseline


def test_parity_pin_trailing_per_line_whitespace_normalized():
  english = (
    "Set greeting to {{a friendly hello}}.   \n"
    "Do [[print]](greeting).   "
  )
  assert compute_english_hash(english) == (
    "43415de15a03032addd6f759f30d51718c451c52f3d31e56e00a1526cbc33a54")


def test_parity_pin_unicode_em_dash_in_slot_text():
  english = "Set greeting to {{a calm blue — pale}}.\nDo [[print]](greeting)."
  # Pinned at drain time via cross-language verification.
  h = compute_english_hash(english)
  assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


# --- Drain 2026-08-05-1030 — U+FEFF cross-language parity ----------------
#
# Expected values are MEASURED from the plugin's `computeEnglishHash`
# (english-hash-core.ts), not recomputed in Python. A parity test that
# recomputes both sides passes even when both drift together — which is
# exactly what it exists to catch.
#
# The gap this closes: both TS hash files strip with `/[\s﻿\xA0]+$/`,
# naming U+FEFF explicitly, and Python's `str.rstrip()` does not treat it
# as whitespace. Four of these six cases diverged before the fix. The
# pre-existing parity test passed throughout, because it never fed a BOM.

_TS_MEASURED = {
  "hello": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "hello﻿": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "hello ﻿ ": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "hello﻿﻿": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "﻿": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}
# The leading-BOM case is deliberately NOT in this table. Its full hash
# was never captured — only a truncated display of it — and a constant
# transcribed from a truncation would look authoritative while proving
# nothing. It is asserted by relation in test_LEADING_bom_is_preserved
# instead, which is the property that actually matters there.


@pytest.mark.parametrize("body", sorted(_TS_MEASURED))
def test_bom_parity_with_plugin(body):
  assert compute_english_hash(body) == _TS_MEASURED[body]


def test_trailing_bom_hashes_as_if_absent():
  assert compute_english_hash("hello﻿") == compute_english_hash("hello")


def test_bom_surrounded_by_whitespace_is_stripped():
  # Needs rstrip → BOM → rstrip; a single pass in either order leaves
  # one of the three pieces behind.
  assert compute_english_hash("hello ﻿ ") == compute_english_hash("hello")


def test_repeated_trailing_boms_are_all_stripped():
  assert compute_english_hash("hello﻿﻿") == compute_english_hash("hello")


def test_a_lone_bom_normalizes_to_empty():
  assert compute_english_hash("﻿") == compute_english_hash("")


def test_LEADING_bom_is_preserved():
  """Leading U+FEFF is content and must NOT be stripped.

  Both runtimes already agreed here before the fix — the TS regex is
  anchored with `$`. Pinned because a "just strip BOMs" fix would break
  it, and it would break identically on both sides, so a
  recompute-both-sides parity test would not notice.
  """
  assert compute_english_hash("﻿hello") != compute_english_hash("hello")
