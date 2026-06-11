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

  # v0.2.73 fix: when slot_resolutions is provided, engine should
  # re-transpile regardless of whether facet_form is present.
  # Returns the Victorian-resolved Python, NOT the stale storybook.
  assert victorian_expr in code, (
    f"v0.2.73 fix: engine MUST re-transpile when slot_resolutions is\n"
    f"provided, regardless of facet_form. Expected Victorian\n"
    f"expression in code; got:\n{code}"
  )
  assert '"Hello, dear reader!"' not in code, (
    f"v0.2.73 fix: stale storybook code MUST NOT survive when\n"
    f"slot_resolutions is provided. Got code:\n{code}"
  )


def test_v0_2_73_slot_resolutions_forces_retranspile_even_when_python_cache_hits_match():
  """v0.2.73 behavior change: when slot_resolutions is provided, the
  engine ALWAYS re-transpiles — the plugin's intent is unambiguous.
  Even on a cache-hit scenario (english_hash matches), the provided
  resolutions win.

  Pre-v0.2.73 behavior: engine returned the cached # Python and
  silently ignored slot_resolutions. v0.2.73: engine respects the
  plugin's intent."""
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
  k = compute_slot_cache_key(
    "a friendly hello message in the style of a children's storybook",
    "forge-moda/slot_demo")
  code = resolve_action_code(snip, slot_resolutions={k: '"DIFFERENT"'})
  # v0.2.73: slot_resolutions wins; re-transpile with new value.
  assert '"DIFFERENT"' in code
  assert '"Hello, dear reader!"' not in code


def test_v0128_force_bypasses_legacy_stored_hash_is_none_rule():
  """v0.2.128 force flag — canonical moda cohort state.

  The bug v0327 confirmed: a snippet with `# English` + `# Python`
  + NO english_hash in frontmatter would hit the legacy
  `stored_hash is None → return cached` rule and return the
  existing `# Python` body verbatim regardless of English edits.

  With force=True the engine MUST skip that rule and re-transpile
  from the current English. Captured Python is the new transpile
  output, NOT the cached body.
  """
  english = 'Do [[print]]("v0128 fresh english").'
  cached_python = (
    'def compute(context):\n'
    '    print("STALE — should not appear when force=True")\n'
  )
  body = (
    f"# English\n\n{english}\n\n"
    f"# Python\n\n```python\n{cached_python}\n```\n"
  )
  snip = {
    "snippet_id": "forge-moda/simulation",
    "meta": {
      "type": "action",
      # NO english_hash — the cohort state for canonical moda snippets.
    },
    "body": body,
  }
  # Without force: legacy rule fires, cached returned.
  cached_result = resolve_action_code(snip)
  assert "STALE" in cached_result
  # With force: cached rule skipped, fresh transpile.
  fresh_result = resolve_action_code(snip, force=True)
  assert "STALE" not in fresh_result
  assert "v0128 fresh english" in fresh_result


def test_v0128_force_bypasses_cache_hit_when_english_hash_matches():
  """v0.2.128 force flag — cohort state after self-heal.

  After the first force-transpile + writeCanonicalPythonBack writes
  english_hash, subsequent clicks WITHOUT force would cache-hit on
  matching hash. With force=True the engine MUST still re-transpile.
  Useful for testing-the-pipeline + future force-on-every-click
  if needed.
  """
  english = 'Do [[print]]("v0128 force overrides cache hit").'
  cached_python = (
    'def compute(context):\n'
    '    print("CACHED — should not appear when force=True")\n'
  )
  matching_hash = compute_english_hash(english)
  body = (
    f"# English\n\n{english}\n\n"
    f"# Python\n\n```python\n{cached_python}\n```\n"
  )
  snip = {
    "snippet_id": "forge-moda/simulation",
    "meta": {
      "type": "action",
      "english_hash": matching_hash,  # cache-hit shape
    },
    "body": body,
  }
  # Without force: cache hits, cached body returned.
  cached_result = resolve_action_code(snip)
  assert "CACHED" in cached_result
  # With force: cache-hit skipped, fresh transpile.
  fresh_result = resolve_action_code(snip, force=True)
  assert "CACHED" not in fresh_result
  assert "v0128 force overrides cache hit" in fresh_result
