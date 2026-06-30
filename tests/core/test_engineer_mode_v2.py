"""Engineer-mode V2 regression suite.

Engineer-mode is the cohort escape hatch for V2-shaped snippets whose
canonical logic lives in `# Python` (because the algorithm is too
complex to express as a Recipe). The frontmatter declares
`edit_mode: python`; the `# Recipe` section is a stub — often an HTML
comment or short prose explanation pointing at the Python.

This suite blocks regressions on the engine's handling of that
pattern. The bug it was born from (v0.2.222, smoke 2026-06-30):

  song.md (V2 normal) → `context.compute("drum_chorus")` → engine
  resolve_action_code → V2 parser → `ParseError: unexpected char '!'
  at line 1, col 2` because drum_chorus.md's Recipe was
  `<!-- engineer-mode: ... -->`.

The plugin's python-mode routing handled the TOP-LEVEL Forge-click
correctly, but the engine had no view of the plugin's routing. The
fix moved the `edit_mode: python` short-circuit BEFORE V2 detection
in `resolve_action_code`.

These tests exercise the engineer-mode path across the matrix:
  - Multiple unparseable-Recipe shapes (HTML comment, prose,
    malformed Call, empty).
  - Direct resolve (top-level Forge-click analogue).
  - Transitive call via context.compute (the song → drum_chorus
    shape that caused the bug).
  - Inverse direction: engineer-mode caller → normal V2 callee.
  - Regression guard: a NON-engineer-mode V2 snippet with an
    unparseable Recipe must still raise (we don't want
    edit_mode: python to leak into accidental tolerance).
"""
import pytest

from forge.core.executor import resolve_action_code, exec_python
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
from forge.core.graph_resolver import GraphResolver


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def _engineer_mode_snippet(snippet_id, recipe_body, python_body,
                           description="A complex snippet."):
  """V2-shaped action snippet with edit_mode: python. Body has
  Description, Recipe (any stub — parseability tested via the
  matrix below), and Python.
  """
  body = (
    f"# Description\n\n{description}\n\n"
    f"# Recipe\n\n{recipe_body}\n\n"
    f"# Python\n\n```python\n{python_body}\n```\n"
  )
  bare = snippet_id.rsplit("/", 1)[-1]
  return {
    "snippet_id": snippet_id,
    "meta": {"type": "action", "edit_mode": "python"},
    "body": body,
    "path": f"{snippet_id}.md",
    "vault": AUTHORING_VAULT,
    "source": "authoring",
  }


def _v2_normal_snippet(snippet_id, recipe_body, python_body=None,
                      description="A normal V2 snippet."):
  """V2-shaped action snippet WITHOUT edit_mode: python — used to test
  the inverse direction (normal caller invoking engineer-mode callee).
  """
  body = f"# Description\n\n{description}\n\n# Recipe\n\n{recipe_body}\n"
  if python_body is not None:
    body += f"\n# Python\n\n```python\n{python_body}\n```\n"
  return {
    "snippet_id": snippet_id,
    "meta": {"type": "action"},
    "body": body,
    "path": f"{snippet_id}.md",
    "vault": AUTHORING_VAULT,
    "source": "authoring",
  }


def _build_registry(*snippets):
  """Register each snippet in AUTHORING_VAULT keyed by bare id."""
  registry = SnippetRegistry()
  registry._vaults.setdefault(AUTHORING_VAULT, {})
  for s in snippets:
    bare = s["snippet_id"].rsplit("/", 1)[-1]
    registry._vaults[AUTHORING_VAULT][bare] = s
  return registry


# -----------------------------------------------------------------
# §1. The matrix: every unparseable-Recipe shape under edit_mode: python
# -----------------------------------------------------------------


UNPARSEABLE_RECIPE_SHAPES = [
  pytest.param(
    "<!-- engineer-mode: this snippet's logic lives in # Python. -->",
    id="html-comment",
  ),
  pytest.param(
    "This snippet uses pure Python; see the # Python section below.",
    id="plain-prose",
  ),
  pytest.param(
    "!@#$%^&*()_+",  # arbitrary punctuation that's not E--
    id="garbage-punctuation",
  ),
  pytest.param(
    "",  # empty body
    id="empty-recipe",
  ),
  pytest.param(
    "Call [[doesnt_exist this is malformed]] with x=??",
    id="malformed-call",
  ),
  pytest.param(
    "TODO: write Recipe later",
    id="todo-marker",
  ),
]


@pytest.mark.parametrize("recipe_body", UNPARSEABLE_RECIPE_SHAPES)
def test_engineer_mode_tolerates_unparseable_recipe(recipe_body):
  """edit_mode: python + ANY Recipe shape (parseable or not) → engine
  returns the # Python facet directly. The Recipe is documentation
  only when edit_mode: python is set."""
  snip = _engineer_mode_snippet(
    "authoring/engineer_snip",
    recipe_body,
    "def compute(context):\n    return 'python-wins'",
  )
  code = resolve_action_code(snip)
  assert "python-wins" in code, (
    f"engineer-mode failed to short-circuit on Recipe shape: {recipe_body!r}"
  )


# -----------------------------------------------------------------
# §2. Transitive call: normal V2 caller → engineer-mode callee
#     (the song → drum_chorus shape that caused v0.2.222)
# -----------------------------------------------------------------


def test_normal_v2_calls_engineer_mode_via_context_compute():
  """Normal V2 snippet's Python calls context.compute on an
  engineer-mode snippet. Engine must resolve the callee via
  edit_mode: python short-circuit instead of trying to V2-parse
  the stub Recipe.

  Regression: pre-v0.2.222 this raised ParseError because the engine
  hit `<!--` in the callee's Recipe.
  """
  callee = _engineer_mode_snippet(
    "authoring/drum_chorus",
    "<!-- engineer-mode -->",
    "def compute(context):\n    return ['kick', 'snare', 'hihat']",
  )
  caller_python = (
    "def compute(context):\n"
    "    drums = context.compute('drum_chorus')\n"
    "    return {'song': 'blues', 'parts': drums}"
  )
  registry = _build_registry(callee)
  resolver = GraphResolver(registry)

  _, result = exec_python(
    caller_python, {}, resolver, snippet_id="authoring/song",
  )
  assert result == {"song": "blues", "parts": ["kick", "snare", "hihat"]}


def test_normal_v2_calls_chain_of_engineer_mode_snippets():
  """Three-link chain: normal caller → engineer-mode A → engineer-mode B.
  Engineer-mode resolution at every transitive hop, not just one."""
  leaf = _engineer_mode_snippet(
    "authoring/leaf",
    "<!-- pure python -->",
    "def compute(context):\n    return 42",
  )
  middle = _engineer_mode_snippet(
    "authoring/middle",
    "TODO Recipe",
    "def compute(context):\n    return context.compute('leaf') * 2",
  )
  caller_python = (
    "def compute(context):\n"
    "    return context.compute('middle') + 1"
  )
  registry = _build_registry(leaf, middle)
  resolver = GraphResolver(registry)

  _, result = exec_python(
    caller_python, {}, resolver, snippet_id="authoring/top",
  )
  assert result == 85  # 42 * 2 + 1


# -----------------------------------------------------------------
# §3. Inverse direction: engineer-mode caller → normal V2 callee
# -----------------------------------------------------------------


def test_engineer_mode_calls_normal_v2_via_context_compute():
  """Engineer-mode snippet's Python invokes a normal-Recipe callee.
  The callee's Recipe IS parseable; the engine should transpile it
  on demand. Validates that engineer-mode doesn't bleed onto the
  callee — only the snippet whose frontmatter declares it gets the
  short-circuit."""
  callee = _v2_normal_snippet(
    "authoring/print_hello",
    'Return "hello".',
  )
  caller = _engineer_mode_snippet(
    "authoring/wrap",
    "<!-- engineer-mode wraps the print -->",
    (
      "def compute(context):\n"
      "    inner = context.compute('print_hello')\n"
      "    return f'wrapped:{inner}'"
    ),
  )
  registry = _build_registry(callee, caller)
  resolver = GraphResolver(registry)

  caller_code = resolve_action_code(caller)
  _, result = exec_python(
    caller_code, {}, resolver, snippet_id=caller["snippet_id"],
  )
  assert result == "wrapped:hello"


# -----------------------------------------------------------------
# §4. Negative: edit_mode: python tolerance MUST be opt-in
# -----------------------------------------------------------------


def test_v2_normal_without_edit_mode_still_raises_on_bad_recipe():
  """The engineer-mode short-circuit applies ONLY when frontmatter
  declares `edit_mode: python`. A V2 snippet WITHOUT that flag and
  with an unparseable Recipe must still surface the parse error —
  silent tolerance would mask cohort typos."""
  body = (
    "# Description\n\nA broken V2 snippet.\n\n"
    "# Recipe\n\n<!-- broken -->\n\n"
    "# Python\n\n```python\ndef compute(context):\n    return 'should-not-reach'\n```\n"
  )
  snip = {
    "snippet_id": "authoring/broken",
    "meta": {"type": "action"},  # no edit_mode
    "body": body,
  }
  from forge.recipe.parser import ParseError
  with pytest.raises(ParseError):
    resolve_action_code(snip)


def test_v2_normal_with_edit_mode_english_still_raises_on_bad_recipe():
  """edit_mode: english is the default; the short-circuit must NOT
  fire for it. Explicit english declaration is treated identically
  to omitted."""
  body = (
    "# Description\n\nA broken V2 snippet.\n\n"
    "# Recipe\n\n<!-- broken -->\n\n"
    "# Python\n\n```python\ndef compute(context):\n    return 'x'\n```\n"
  )
  snip = {
    "snippet_id": "authoring/broken_explicit",
    "meta": {"type": "action", "edit_mode": "english"},
    "body": body,
  }
  from forge.recipe.parser import ParseError
  with pytest.raises(ParseError):
    resolve_action_code(snip)


# -----------------------------------------------------------------
# §5. Edge: edit_mode: python with NO # Python facet → don't crash;
#     fall through to the existing V1-style codepath that returns
#     None (plugin handles via /generate).
# -----------------------------------------------------------------


def test_engineer_mode_without_python_facet_does_not_short_circuit():
  """If somehow a snippet declares edit_mode: python but has no
  # Python section (cohort mid-edit, broken vault state), the
  short-circuit must not crash. extract_python returns None → we
  fall through to the V2 path (which itself will surface a clear
  error or transpile attempt)."""
  body = (
    "# Description\n\nMissing Python.\n\n"
    "# Recipe\n\nReturn 1.\n"
  )
  snip = {
    "snippet_id": "authoring/missing_python",
    "meta": {"type": "action", "edit_mode": "python"},
    "body": body,
  }
  # Recipe is parseable; V2 path should handle it without the
  # short-circuit firing (because extract_python returns None).
  code = resolve_action_code(snip)
  # The V2 transpile of `Return 1.` should produce something runnable.
  assert code is not None
  assert "1" in code
