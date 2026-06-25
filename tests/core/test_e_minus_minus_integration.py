"""Tests for E-- integration via `forge.core.executor.resolve_action_code`.

v0.2.121 — facet_form removed (Option C plugin-side routing). The
engine always attempts E-- transpile; returns None on
EmmSyntaxError so the plugin's routeActionCodeRegen wrapper can
fall back to /generate (LLM).

Tests cover:

  1. Python facet present + matching english_hash → returns Python
     verbatim (cache hit).
  2. Valid English (E-- compatible) → returns E-- transpile output.
  3. Missing # English heading → returns None (plugin falls back).
  4. E-- syntax error (free-text English) → returns None (plugin
     falls back to /generate).
  5. Idempotent rider: same body twice → same Python out.
  6. End-to-end via ForgeContext.compute: canonical snippet
     transpiles + executes.
  7. Bundle smoke: vendored E-- module is importable.

Note: Pre-v0.2.121 tests for `facet_form: free` and absent-
`facet_form` keys are deleted — these gates no longer exist in
the engine. The plugin's routeActionCodeRegen handles routing.
"""

import pytest
from forge.core.executor import resolve_action_code
from forge.e_minus_minus import EmmSyntaxError


def _snippet(body, snippet_id="test/sample"):
    """Build a minimal snippet dict matching what snippet_registry
    produces. v0.2.121 — facet_form arg removed; the field is
    inert engine-side."""
    return {
        "body": body,
        "meta": {"type": "action"},
        "snippet_id": snippet_id,
    }


# --- resolve_action_code ---

def test_python_facet_without_english_hash_returns_verbatim():
    """When `# Python` is present AND no `english_hash` is stored
    (legacy snippet or hand-authored Python from before the
    english_hash invalidation contract), the engine returns the
    cached Python directly per the v0.2.121 legacy preservation
    rule. See `resolve_action_code` docstring: "If english_hash
    is ABSENT → no invalidation contract on this snippet; return
    the cached code."

    This preserves backward compatibility for snippets predating
    the english_hash mechanism. Modern snippets use one of:
      - `english_hash` for cache-validated freshness (see
        test_cache_hit_when_english_hash_matches)
      - `edit_mode: python` for explicit author-canonical Python
      - V2 `# E--` facet for transpiled-recipe authoring

    Pre-v0.2.182 this test had a stale assertion (`code is None`)
    inherited from a docstring that admitted it was "exercising a
    different branch." Fixed to match the documented + implemented
    legacy preservation behavior.
    """
    body = (
        "# Python\n"
        '```python\n'
        'def compute(context):\n'
        '  print("hi")\n'
        '```\n'
    )
    code = resolve_action_code(_snippet(body))
    assert code is not None
    assert 'print("hi")' in code


def test_cache_hit_when_english_hash_matches():
    """When `# Python` is present AND english_hash matches the current
    # English content's hash, the engine returns the cached Python
    directly without re-transpiling."""
    from forge.core.slot_cache import compute_english_hash
    english = "Do [[print]](\"cached\")."
    body = (
        "# English\n"
        f"{english}\n"
        "# Python\n"
        '```python\n'
        'def compute(context):\n'
        '  print("cached")\n'
        '```\n'
    )
    snip = _snippet(body)
    snip["meta"]["english_hash"] = compute_english_hash(english)
    code = resolve_action_code(snip)
    assert code is not None
    assert 'print("cached")' in code


def test_emm_compatible_english_transpiles():
    """When the English is valid E--, the engine transpiles it
    regardless of facet_form. Replaces the v0.2.121-retired
    `test_canonical_facet_form_transpiles_via_emm`."""
    body = (
        "# English\n"
        'Do [[print]]("E-- transpile works").\n'
    )
    code = resolve_action_code(_snippet(body))
    # E-- emits the bare expression; resolve_action_code wraps it
    # in `def compute(context):` so exec_python's _find_entrypoint
    # contract is satisfied.
    assert code == (
        'def compute(context):\n'
        '    print("E-- transpile works")'
    )


def test_missing_english_heading_returns_none():
    """v0.2.121 — when there's no # English heading, return None so
    the plugin falls back to /generate (or surfaces a clear error
    when no token is set). Replaces the v0.2.120-and-prior
    behavior of raising ValueError."""
    body = (
        "# Body\n"
        "(no English heading)\n"
    )
    code = resolve_action_code(_snippet(body, snippet_id="test/no_english"))
    assert code is None


def test_emm_syntax_error_returns_none():
    """v0.2.121 — when the English contains E-- syntax that the
    transpiler can't parse (free-text English, missing terminator,
    etc.), the engine returns None so the plugin falls back to
    /generate. Replaces the v0.2.120-and-prior behavior of raising
    ValueError. The plugin's routeActionCodeRegen interprets None
    as 'try the LLM path'."""
    body = (
        "# English\n"
        'Do [[print]]("missing terminator")\n'
    )
    code = resolve_action_code(_snippet(body, snippet_id="test/bad_syntax"))
    assert code is None


def test_free_text_english_returns_none():
    """Free-text English (the cohort onboarding path) returns None
    so the plugin falls back to /generate. This is the most common
    case under v0.2.121's Option C routing."""
    body = (
        "# English\n"
        "Please print a friendly hello to the user.\n"
    )
    code = resolve_action_code(_snippet(body))
    assert code is None


def test_emm_transpile_idempotent():
    """Transpiling the same canonical body twice produces the same
    Python — important because the engine may resolve_action_code
    multiple times during a single Forge-click."""
    body = (
        "# English\n"
        'Do [[print]]("hello").\n'
    )
    snip = _snippet(body)
    a = resolve_action_code(snip)
    b = resolve_action_code(snip)
    assert a == b
    assert a is not None


# --- end-to-end via exec_python ---

def test_emm_transpile_executes_correctly():
    """End-to-end: a snippet with E--compatible English → engine
    transpiles via E-- → executes through exec_python → result
    matches the expected stdout."""
    body = (
        "# English\n"
        'Do [[print]]("e2e canonical").\n'
    )
    code = resolve_action_code(_snippet(body, snippet_id="test/demo"))
    assert code is not None
    assert code.startswith('def compute(context):')
    assert 'print("e2e canonical")' in code

    from forge.core.executor import exec_python
    stdout, _result = exec_python(
        code, inputs={}, snippet_id="test/demo",
    )
    assert "e2e canonical" in stdout


# --- bundle smoke ---

def test_emm_module_importable_from_forge_e_minus_minus():
    """Sanity: the vendored package is importable + exposes
    transpile. End-to-end deterministic compile through the
    vendored API."""
    from forge.e_minus_minus import transpile
    assert callable(transpile)
    assert transpile('Do [[print]]("z").') == 'print("z")'

    # EmmSyntaxError is the documented failure surface (used by
    # resolve_action_code to detect free-text English).
    with pytest.raises(EmmSyntaxError):
        transpile('not valid e-- syntax at all')
