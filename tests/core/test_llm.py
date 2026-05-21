"""Tests for forge.core.llm helpers that don't need an actual LLM call."""
from forge.core.llm import _find_deps, _build_prompt


def test_build_prompt_includes_description_inputs_english():
  meta = {"description": "Hello.", "inputs": ["x"]}
  body = "# English\nReturn x.\n# Python\n"
  prompt = _build_prompt("hello", meta, body, deps=[], registry=None)
  assert "Description: Hello." in prompt
  assert "Inputs: x" in prompt
  assert "Behavior:" in prompt and "Return x." in prompt


def test_build_prompt_passes_generation_notes_when_present():
  meta = {
    "description": "Block 15.",
    "inputs": ["pairs"],
    "generation_notes": "Pure dispatch. Do not recompute the predicate.",
  }
  body = "# English\nIf colliding: call bounce_off_particle.\n# Python\n"
  prompt = _build_prompt("if_particle_then_bounce", meta, body,
                         deps=[], registry=None)
  assert "Generation notes" in prompt
  assert "Do not recompute the predicate." in prompt


def test_build_prompt_omits_generation_notes_when_absent():
  meta = {"description": "Plain.", "inputs": []}
  body = "# English\nDo a thing.\n"
  prompt = _build_prompt("plain", meta, body, deps=[], registry=None)
  assert "Generation notes" not in prompt


# Canonicalize system-prompt composition — the /canonicalize endpoint
# threads active_domains so the domain's English style overrides the
# default narrative-prose voice.
from forge.core.llm import _build_canonicalize_system_prompt, _CANONICALIZE_SYSTEM_PROMPT


def test_canonicalize_prompt_no_domains_uses_base():
  assert _build_canonicalize_system_prompt(None) is _CANONICALIZE_SYSTEM_PROMPT
  assert _build_canonicalize_system_prompt([]) is _CANONICALIZE_SYSTEM_PROMPT


def test_canonicalize_prompt_moda_appends_procedural_style_override():
  out = _build_canonicalize_system_prompt(["moda"])
  assert out.startswith(_CANONICALIZE_SYSTEM_PROMPT)
  # Moda override teaches the procedural-line shape.
  assert "Moda block-style override" in out
  # Anchor on phrases that are reliably on a single line in the
  # override text (which has hard wraps embedded as \n).
  assert "procedural-\nline shape" in out or "procedural-line shape" in out
  # Inputs line is MANDATORY in the moda voice.
  assert "Inputs:" in out
  assert "MANDATORY" in out
  # The state-resolution prelude becomes trailing prose, NOT a
  # procedural line — this is the key shape correction.
  assert "History-dependent per C8" in out
  # No-wikilinks-in-body / no-implementation-directives constraints.
  assert "[[wikilinks]]" in out
  assert "generation_notes" in out
  # Reference shape (concrete go.md example) anchors the LLM.
  assert "Call ask_all_particles with dt" in out


def test_canonicalize_prompt_unknown_domain_silently_ignored():
  # Domain we don't have a canonicalize override for falls through
  # to the base voice rather than raising.
  out = _build_canonicalize_system_prompt(["future-domain-no-override"])
  assert out is _CANONICALIZE_SYSTEM_PROMPT


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
  """Legacy alias `locked: true` keeps working for one release cycle.
  Same skip path as `edit_mode: python`."""
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


def test_generate_skips_python_edit_mode_snippets(monkeypatch):
  """`edit_mode: python` is the canonical signal that a snippet's python
  facet is hand-tuned — _generate skips it the same way as the builtin
  skip, no LLM, no recursion into deps."""
  from forge.core.llm import generate_snippet_code
  from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT

  reg = SnippetRegistry()
  reg._vaults[AUTHORING_VAULT] = {
    "tweaked": {
      "meta": {"type": "action", "edit_mode": "python"},
      "body": '# English\nDo X.\n# Python\n```python\ndef compute(context):\n  return 1\n```',
      "path": "/v/tweaked.md",
      "vault": AUTHORING_VAULT,
      "vault_path": "/v",
      "source": "authoring",
      "snippet_id": f"{AUTHORING_VAULT}/tweaked",
    },
  }

  def fail(*args, **kwargs):
    raise AssertionError("LLM should not be called when edit_mode=python")
  monkeypatch.setattr("forge.core.llm._call_llm", fail)

  result = generate_snippet_code("tweaked", reg, recursive=True)
  assert result == {}


def test_canonicalize_python_returns_llm_text(monkeypatch):
  """canonicalize_python wraps the LLM call with a focused system prompt
  and a python-only user message; verify the function packages the call
  shape correctly and returns the model's text."""
  from forge.core import llm
  from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT

  reg = SnippetRegistry()
  reg._vaults[AUTHORING_VAULT] = {
    "tweaked": {
      "meta": {"type": "action", "description": "make a thing"},
      "body": (
        '# English\nold english\n# Python\n```python\n'
        'def compute(context):\n  return context.compute("dep") + 1\n```'
      ),
      "path": "/v/tweaked.md",
      "vault": AUTHORING_VAULT,
      "vault_path": "/v",
      "source": "authoring",
      "snippet_id": f"{AUTHORING_VAULT}/tweaked",
    },
  }

  captured = {}

  class FakeMsg:
    def __init__(self, text):
      self.content = [type("C", (), {"text": text})()]

  class FakeMessages:
    def create(self, **kwargs):
      captured.update(kwargs)
      return FakeMsg("Calls [[dep]] and adds one to its result.")

  class FakeClient:
    messages = FakeMessages()

  monkeypatch.setattr(llm, "_get_client", lambda: FakeClient())

  result = llm.canonicalize_python("tweaked", reg)
  assert result == "Calls [[dep]] and adds one to its result."
  # The user message should embed the python facet and the snippet id.
  user = captured["messages"][0]["content"]
  assert "tweaked" in user
  assert "context.compute(\"dep\")" in user
  # The system prompt should be the canonicalize-specific one, not the
  # standard generation prompt.
  assert "summarizing Forge snippets" in captured["system"]


def test_canonicalize_python_raises_when_python_facet_empty():
  from forge.core.llm import canonicalize_python
  from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
  import pytest

  reg = SnippetRegistry()
  reg._vaults[AUTHORING_VAULT] = {
    "blank": {
      "meta": {"type": "action"},
      "body": "# English\nintent only\n",
      "path": "/v/blank.md",
      "vault": AUTHORING_VAULT,
      "vault_path": "/v",
      "source": "authoring",
      "snippet_id": f"{AUTHORING_VAULT}/blank",
    },
  }
  with pytest.raises(ValueError, match="no Python facet"):
    canonicalize_python("blank", reg)


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
