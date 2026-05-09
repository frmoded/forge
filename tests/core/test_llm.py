"""Tests for forge.core.llm helpers that don't need an actual LLM call."""
from forge.core.llm import _find_deps


def test_find_deps_picks_up_real_wikilinks():
  body = "See also [[chorus]] and [[song]]."
  assert _find_deps(body) == ["chorus", "song"]


def test_find_deps_handles_aliased_wikilinks():
  body = "Discussed in [[song|the song]]."
  assert _find_deps(body) == ["song"]


def test_find_deps_picks_up_qualified_ids():
  body = 'context.compute("forge/registry/lookup")'
  assert _find_deps(body) == ["forge/registry/lookup"]


def test_find_deps_skips_prose_placeholders():
  """Prose like '[[<vault_name>/...]]' in English / docstrings or f-strings
  like '[[{vault_name}/...]]' are documentation, not snippet refs. They were
  triggering recursive /generate to 404 on phantom deps before the regex got
  tightened to require valid ID chars only."""
  body = (
    "After install, try [[<vault_name>/...]] to invoke any of its snippets."
  )
  assert _find_deps(body) == []


def test_find_deps_skips_curly_brace_placeholders():
  body = 'message = f"now try [[{vault_name}/...]] to invoke."'
  assert _find_deps(body) == []


def test_find_deps_dedups_repeats():
  body = "[[chorus]] then [[chorus]] again."
  assert _find_deps(body) == ["chorus"]


def test_find_deps_combines_wikilink_and_compute():
  body = '[[chorus]] then context.compute("forge/registry/lookup")'
  assert _find_deps(body) == ["chorus", "forge/registry/lookup"]


def test_generate_skips_locked_snippets(monkeypatch):
  """`locked: true` in frontmatter freezes the python facet — recursive
  /generate must not call the LLM for a locked snippet (and must not walk
  its deps either, since the parent's prompt embeds dep signatures only,
  not bodies)."""
  from forge.core.llm import generate_snippet_code
  from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT

  reg = SnippetRegistry()
  reg._vaults[AUTHORING_VAULT] = {
    "frozen": {
      "meta": {"type": "action", "locked": True},
      "body": '# English\nDo X.\n# Python\n```python\ndef compute(context):\n  return 1\n```',
      "path": "/v/frozen.md",
      "vault": AUTHORING_VAULT,
      "vault_path": "/v",
      "source": "authoring",
      "snippet_id": f"{AUTHORING_VAULT}/frozen",
    },
  }

  def fail(*args, **kwargs):
    raise AssertionError("LLM should not be called for locked snippets")
  monkeypatch.setattr("forge.core.llm._call_llm", fail)

  result = generate_snippet_code("frozen", reg, recursive=True)
  assert result == {}


def test_generate_skips_builtin_snippets(monkeypatch):
  """Builtins ship with python in the package — _generate should skip them
  rather than spending LLM tokens regenerating working code (and producing
  results the client has no user-vault file to write back to)."""
  from forge.core.llm import generate_snippet_code
  from forge.core.snippet_registry import SnippetRegistry, BUILTIN_VAULT

  reg = SnippetRegistry()
  reg._vaults[BUILTIN_VAULT] = {
    "install": {
      "meta": {"type": "action", "inputs": ["vault_name"]},
      "body": '# English\nInstall a vault.\n# Python\n```python\ndef compute(context, vault_name):\n  context.compute("forge/registry/lookup")\n```',
      "path": "/builtin/install.md",
      "vault": BUILTIN_VAULT,
      "vault_path": "/builtin",
      "source": "builtin",
      "snippet_id": "forge/install",
    },
    "registry/lookup": {
      "meta": {"type": "action"},
      "body": "# Python\n```python\ndef compute(context):\n  pass\n```",
      "path": "/builtin/registry/lookup.md",
      "vault": BUILTIN_VAULT,
      "vault_path": "/builtin",
      "source": "builtin",
      "snippet_id": "forge/registry/lookup",
    },
  }

  # Fail loudly if anything tries to call the LLM.
  def fail(*args, **kwargs):
    raise AssertionError("LLM should not be called for builtin snippets")
  monkeypatch.setattr("forge.core.llm._call_llm", fail)

  result = generate_snippet_code("install", reg, recursive=True)
  assert result == {}
