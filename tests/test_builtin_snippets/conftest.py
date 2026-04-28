import pytest
from forge.builtins.loader import load_builtin_vault
from forge.core.executor import extract_python, exec_python
from forge.core.snippet_registry import SnippetRegistry
from forge.core.graph_resolver import GraphResolver


def _find(snippets, snippet_id):
  for s in snippets:
    if s["snippet_id"] == snippet_id:
      return s
  raise KeyError(f"builtin snippet {snippet_id!r} not loaded")


@pytest.fixture
def builtin_snippets():
  return load_builtin_vault()


@pytest.fixture
def registry_with_builtins(builtin_snippets):
  reg = SnippetRegistry()
  reg.register_builtin_vault(builtin_snippets)
  return reg


@pytest.fixture
def run_builtin(builtin_snippets, registry_with_builtins):
  """Execute a built-in snippet by ID. Returns (stdout, result)."""
  resolver = GraphResolver(registry_with_builtins)

  def _run(snippet_id, vault_path=None, registry=None, **kwargs):
    snippet = _find(builtin_snippets, snippet_id)
    code = extract_python(snippet["body"])
    return exec_python(
      code, kwargs, resolver,
      vault_path=vault_path,
      registry=registry if registry is not None else registry_with_builtins,
      trusted=True,
    )
  return _run
