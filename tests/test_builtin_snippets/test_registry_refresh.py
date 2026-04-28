from pathlib import Path
import pytest
from forge.builtins.loader import load_builtin_vault
from forge.core.executor import extract_python, exec_python, SnippetExecError
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
from forge.core.graph_resolver import GraphResolver


_SNIPPET_TEXT = """\
---
type: action
description: tiny seed snippet for refresh tests
---

# Python

```python
def run(context):
  return 1
```
"""


def _vault_with_snippet(tmp_path: Path, name: str = "demo") -> Path:
  vault = tmp_path / "vault"
  vault.mkdir()
  (vault / f"{name}.md").write_text(_SNIPPET_TEXT)
  return vault


def test_refresh_rescans_authoring_vault(builtin_snippets, tmp_path):
  vault = _vault_with_snippet(tmp_path, "demo")

  registry = SnippetRegistry()
  # initial scan finds nothing yet — file already exists, but force a fresh registry
  registry.register_builtin_vault(builtin_snippets)
  resolver = GraphResolver(registry)
  assert registry.get_in_vault(AUTHORING_VAULT, "demo") is None

  snippet = next(s for s in builtin_snippets if s["snippet_id"] == "forge/registry/refresh")
  code = extract_python(snippet["body"])
  _, result = exec_python(
    code, {}, resolver,
    vault_path=str(vault),
    registry=registry,
    trusted=True,
  )

  assert result["refreshed"] is True
  assert result["vault_path"] == str(vault)
  # the new snippet is now indexed under the authoring vault
  assert registry.get_in_vault(AUTHORING_VAULT, "demo") is not None
  # builtins are still present
  assert registry.get_in_vault("forge", "registry/refresh") is not None


def test_refresh_picks_up_newly_added_snippets(builtin_snippets, tmp_path):
  vault = _vault_with_snippet(tmp_path, "first")

  registry = SnippetRegistry()
  registry.scan(str(vault))  # seed authoring with first.md
  registry.register_builtin_vault(builtin_snippets)
  resolver = GraphResolver(registry)
  assert registry.get_in_vault(AUTHORING_VAULT, "first") is not None
  assert registry.get_in_vault(AUTHORING_VAULT, "second") is None

  # simulate a freshly installed library file landing in the vault
  (vault / "second.md").write_text(_SNIPPET_TEXT)

  snippet = next(s for s in builtin_snippets if s["snippet_id"] == "forge/registry/refresh")
  code = extract_python(snippet["body"])
  exec_python(
    code, {}, resolver,
    vault_path=str(vault),
    registry=registry,
    trusted=True,
  )

  assert registry.get_in_vault(AUTHORING_VAULT, "first") is not None
  assert registry.get_in_vault(AUTHORING_VAULT, "second") is not None


def test_refresh_requires_vault_path(builtin_snippets):
  registry = SnippetRegistry()
  registry.register_builtin_vault(builtin_snippets)
  resolver = GraphResolver(registry)

  snippet = next(s for s in builtin_snippets if s["snippet_id"] == "forge/registry/refresh")
  code = extract_python(snippet["body"])
  with pytest.raises(SnippetExecError):
    exec_python(code, {}, resolver, registry=registry, trusted=True)


def test_notify_clients_hook_is_callable(builtin_snippets):
  """Until Chunk E broadcasts, the stub must at least exist and be reachable."""
  snippet = next(s for s in builtin_snippets if s["snippet_id"] == "forge/registry/refresh")
  code = extract_python(snippet["body"])
  ns = {"__builtins__": __builtins__}
  exec(compile(code, "<snippet>", "exec"), ns)
  assert callable(ns.get("_notify_clients"))
  # the hook is currently a no-op
  assert ns["_notify_clients"](None) is None
