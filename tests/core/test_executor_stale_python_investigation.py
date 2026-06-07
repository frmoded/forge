"""v0.2.73 — investigation test for Hypothesis B (engine returns stale
# Python on second pass despite slot_resolutions being supplied).

Reproduces the on-disk state after Step 5 of the v0.2.72 smoke:
- # Python: storybook code from first compute.
- # English: Victorian text after user edit.
- english_hash in frontmatter: storybook hash (stale; matches storybook
  English, NOT Victorian).
- facet_form: canonical.
- edit_mode: english (default).

When the plugin calls resolve_action_code(snip, slot_resolutions=...)
on this state, the engine SHOULD detect the english_hash mismatch and
fall through to the transpile path with the resolutions dict — NOT
return the cached storybook code.

If this test PASSES against current v0.2.72 code: Hypothesis B refuted.
If it FAILS: Hypothesis B confirmed.
"""
import pytest

from forge.core.executor import resolve_action_code
from forge.core.slot_cache import compute_english_hash, compute_slot_cache_key


def test_hypothesis_b_engine_returns_fresh_code_on_slot_resolutions_with_stale_python():
  """The exact reproduction: stored # Python + stale english_hash +
  Victorian English + slot_resolutions provided. Engine must NOT
  short-circuit on the cached # Python; must re-transpile with
  resolutions."""
  storybook_python = (
    'def compute(context):\n'
    '    greeting = "Hello, dear reader!"\n'
    '    print(greeting)'
  )
  storybook_english_old = (
    "Set greeting to {{a friendly hello message in the style of a "
    "children's storybook}}.\nDo [[print]](greeting)."
  )
  stored_hash = compute_english_hash(storybook_english_old)

  victorian_english_new = (
    'Set greeting to {{a formal hello message in the style of a '
    'Victorian letter}}.\nDo [[print]](greeting).'
  )
  snippet_id = "forge-moda/slot_demo"

  body = (
    f"# English\n\n{victorian_english_new}\n\n"
    f"# Python\n\n```python\n{storybook_python}\n```\n"
  )

  snip = {
    "snippet_id": snippet_id,
    "meta": {
      "type": "action",
      "facet_form": "canonical",
      "inputs": [],
      "english_hash": stored_hash,
    },
    "body": body,
  }

  # Plugin provides slot_resolutions for the new Victorian slot.
  victorian_expr = '"Good day to you, esteemed reader."'
  new_slot_text = (
    "a formal hello message in the style of a Victorian letter")
  k = compute_slot_cache_key(new_slot_text, snippet_id)
  resolutions = {k: victorian_expr}

  code = resolve_action_code(snip, slot_resolutions=resolutions)

  # Engine MUST return the Victorian-resolved Python, NOT the stored
  # storybook code.
  assert isinstance(code, str)
  assert victorian_expr in code, (
    f"Expected Victorian expression {victorian_expr!r} in returned "
    f"code, got:\n{code}"
  )
  assert '"Hello, dear reader!"' not in code, (
    f"STALE storybook code survived the second pass. Engine returned:\n{code}"
  )


def test_hypothesis_b_engine_short_circuits_when_english_hash_matches():
  """Sanity check: when english_hash MATCHES and slot_resolutions is
  None (first compute on a cached snippet), engine returns the cached
  # Python without re-transpile. This is the cache-hit path the
  v0.2.72 contract documents."""
  python = (
    'def compute(context):\n'
    '    greeting = "Hello, dear reader!"\n'
    '    print(greeting)'
  )
  english = (
    "Set greeting to {{a friendly hello message in the style of a "
    "children's storybook}}.\nDo [[print]](greeting)."
  )
  matching_hash = compute_english_hash(english)
  body = (
    f"# English\n\n{english}\n\n"
    f"# Python\n\n```python\n{python}\n```\n"
  )
  snip = {
    "snippet_id": "forge-moda/slot_demo",
    "meta": {
      "type": "action",
      "facet_form": "canonical",
      "inputs": [],
      "english_hash": matching_hash,
    },
    "body": body,
  }
  code = resolve_action_code(snip)
  assert '"Hello, dear reader!"' in code


def test_hypothesis_c_engine_returns_stale_python_when_facet_form_absent():
  """Hypothesis C: if Obsidian's YAML serializer drops the
  `facet_form: canonical` field (e.g., on a frontmatter rewrite after
  the user's English edit), the engine takes the legacy "no facet_form"
  branch at executor.py:511 and returns the cached `# Python` regardless
  of english_hash. The plugin then writes stale storybook to # Python
  + new Victorian hash to frontmatter. Matches the user's observation.

  If this test PASSES (engine returns stale code), Hypothesis C is
  the confirmed root cause."""
  storybook_python = (
    'def compute(context):\n'
    '    greeting = "Hello, dear reader!"\n'
    '    print(greeting)'
  )
  storybook_english_old = (
    "Set greeting to {{a friendly hello message in the style of a "
    "children's storybook}}.\nDo [[print]](greeting)."
  )
  stored_hash = compute_english_hash(storybook_english_old)

  victorian_english_new = (
    'Set greeting to {{a formal hello message in the style of a '
    'Victorian letter}}.\nDo [[print]](greeting).'
  )
  snippet_id = "forge-moda/slot_demo"

  body = (
    f"# English\n\n{victorian_english_new}\n\n"
    f"# Python\n\n```python\n{storybook_python}\n```\n"
  )

  # facet_form INTENTIONALLY ABSENT — simulating Obsidian dropping it.
  snip = {
    "snippet_id": snippet_id,
    "meta": {
      "type": "action",
      # NO facet_form field at all.
      "inputs": [],
      "english_hash": stored_hash,
    },
    "body": body,
  }

  victorian_expr = '"Good day to you, esteemed reader."'
  new_slot_text = (
    "a formal hello message in the style of a Victorian letter")
  k = compute_slot_cache_key(new_slot_text, snippet_id)
  resolutions = {k: victorian_expr}

  code = resolve_action_code(snip, slot_resolutions=resolutions)

  # If Hypothesis C holds, the engine returns STALE storybook code
  # regardless of slot_resolutions, because the facet_form != "canonical"
  # branch takes precedence over the hash check.
  assert '"Hello, dear reader!"' in code, (
    f"Hypothesis C INTENDS that the engine returns the stale # Python\n"
    f"when facet_form is absent. If this assertion fails, the engine\n"
    f"actually re-transpiles even without facet_form — meaning\n"
    f"Hypothesis C is also refuted and the bug is elsewhere.\n"
    f"Actual code:\n{code}"
  )
  # The Victorian expression should NOT be in the returned code.
  assert victorian_expr not in code, (
    f"Hypothesis C says engine returns OLD storybook; the new\n"
    f"Victorian expression should be absent. Got code:\n{code}"
  )


def test_hypothesis_b_slot_resolutions_ignored_when_python_cache_hits_match():
  """Edge case to characterize: when english_hash matches AND
  slot_resolutions is provided (could happen if plugin pessimistically
  passes resolutions even on a cache hit), what does the engine do?

  v0.2.72 implementation returns the cached # Python. This is fine —
  the cache-hit path documents that # Python wins."""
  python = (
    'def compute(context):\n'
    '    greeting = "Hello, dear reader!"\n'
    '    print(greeting)'
  )
  english = (
    "Set greeting to {{a friendly hello message in the style of a "
    "children's storybook}}.\nDo [[print]](greeting)."
  )
  matching_hash = compute_english_hash(english)
  body = (
    f"# English\n\n{english}\n\n"
    f"# Python\n\n```python\n{python}\n```\n"
  )
  snip = {
    "snippet_id": "forge-moda/slot_demo",
    "meta": {
      "type": "action",
      "facet_form": "canonical",
      "inputs": [],
      "english_hash": matching_hash,
    },
    "body": body,
  }
  # Provide a different resolution; cache hit should still return the
  # cached Python (ignore the provided resolutions).
  k = compute_slot_cache_key(
    "a friendly hello message in the style of a children's storybook",
    "forge-moda/slot_demo")
  code = resolve_action_code(snip, slot_resolutions={k: '"DIFFERENT"'})
  assert '"Hello, dear reader!"' in code
