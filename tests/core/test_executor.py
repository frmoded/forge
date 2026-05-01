import pytest
from forge.core.executor import extract_python, extract_section, exec_python, SnippetExecError


def test_extract_python_fenced():
  body = "# Python\n\n```python\nresult = 1\n```"
  assert extract_python(body) == "result = 1"


def test_extract_python_unfenced():
  body = "# Python\nresult = 1"
  assert extract_python(body) == "result = 1"


def test_extract_python_missing_heading():
  assert extract_python("no heading here") is None


def test_extract_python_stops_at_next_heading():
  body = "# Python\ncode = 1\n# Other\nother = 2"
  assert extract_python(body) == "code = 1"


def test_extract_section_plain_text():
  body = "# English\nhello world\n\n---\n\n# Python\ncode"
  assert extract_section(body, "english") == "hello world"


def test_extract_section_case_insensitive():
  body = "## ENGLISH\nhello\n# Python\ncode"
  assert extract_section(body, "english") == "hello"


def test_extract_section_missing():
  assert extract_section("no sections here", "english") is None


def test_exec_python_captures_stdout():
  code = "def compute(context):\n  print('hi')"
  stdout, _ = exec_python(code, {})
  assert stdout == "hi\n"


def test_exec_python_compute_convention():
  code = "def compute(context):\n  return 42"
  _, result = exec_python(code, {})
  assert result == 42


def test_exec_python_compute_with_named_inputs():
  code = "def compute(context, name):\n  return f'Hello {name}'"
  _, result = exec_python(code, {"name": "Alice"})
  assert result == "Hello Alice"


def test_exec_python_random_in_scope():
  code = "def compute(context):\n  return random.randint(5, 5)"
  _, result = exec_python(code, {})
  assert result == 5


def test_exec_python_math_in_scope():
  code = "def compute(context):\n  return math.floor(3.9)"
  _, result = exec_python(code, {})
  assert result == 3


def test_exec_python_blocks_import():
  code = "def compute(context):\n  import os\n  return os"
  with pytest.raises(SnippetExecError):
    exec_python(code, {})


def test_exec_python_raises_snippet_exec_error_with_stdout():
  code = "def compute(context):\n  print('before')\n  raise ValueError('boom')"
  with pytest.raises(SnippetExecError) as exc_info:
    exec_python(code, {})
  assert "boom" in str(exc_info.value)
  assert "before" in exc_info.value.stdout


def test_exec_python_raises_when_no_compute_function():
  """Strict: a snippet's Python facet must declare def compute."""
  code = "x = 1"
  with pytest.raises(SnippetExecError, match="no def compute"):
    exec_python(code, {})


def test_exec_python_error_includes_snippet_id_when_provided():
  code = "x = 1"
  with pytest.raises(SnippetExecError, match="snippet 'forge-core/hello_registry'"):
    exec_python(code, {}, snippet_id="forge-core/hello_registry")


# --- Trust + context-state extensions (Chunk C runtime support) ---

def test_context_exposes_vault_path():
  code = "def compute(context):\n  return context.vault_path"
  _, result = exec_python(code, {}, vault_path="/some/vault")
  assert result == "/some/vault"


def test_context_exposes_registry():
  from forge.core.snippet_registry import SnippetRegistry
  reg = SnippetRegistry()
  code = "def compute(context):\n  return context.registry is not None"
  _, result = exec_python(code, {}, registry=reg)
  assert result is True


def test_trusted_permits_import():
  code = "def compute(context):\n  import os\n  return os.path.sep"
  _, result = exec_python(code, {}, trusted=True)
  assert result in ("/", "\\")


def test_untrusted_blocks_import():
  code = "def compute(context):\n  import os\n  return os"
  with pytest.raises(SnippetExecError):
    exec_python(code, {}, trusted=False)


def test_trusted_permits_open(tmp_path):
  p = tmp_path / "data.txt"
  p.write_text("hello")
  code = f"def compute(context):\n  with open({str(p)!r}) as f:\n    return f.read()"
  _, result = exec_python(code, {}, trusted=True)
  assert result == "hello"


def test_nested_execute_propagates_vault_path():
  from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
  from forge.core.graph_resolver import GraphResolver

  inner_code = "def compute(context):\n  return context.vault_path"
  outer_code = "def compute(context):\n  return context.compute('inner')"

  registry = SnippetRegistry()
  registry._vaults.setdefault(AUTHORING_VAULT, {})
  registry._vaults[AUTHORING_VAULT]["inner"] = {
    "meta": {"type": "action"},
    "body": f"# Python\n\n```python\n{inner_code}\n```",
    "path": "",
    "vault": AUTHORING_VAULT,
    "source": "authoring",
    "snippet_id": "authoring/inner",
  }
  resolver = GraphResolver(registry)
  _, result = exec_python(outer_code, {}, resolver, vault_path="/v", registry=registry)
  assert result == "/v"


def test_nested_execute_grants_trust_only_to_builtins():
  from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
  from forge.core.graph_resolver import GraphResolver

  # The user-authored "inner" snippet tries to import — should fail even though
  # the parent (which calls it) ran trusted.
  inner_code = "def compute(context):\n  import os\n  return os.path.sep"
  outer_code = "def compute(context):\n  return context.compute('inner')"

  registry = SnippetRegistry()
  registry._vaults.setdefault(AUTHORING_VAULT, {})
  registry._vaults[AUTHORING_VAULT]["inner"] = {
    "meta": {"type": "action"},
    "body": f"# Python\n\n```python\n{inner_code}\n```",
    "path": "",
    "vault": AUTHORING_VAULT,
    "source": "authoring",
    "snippet_id": "authoring/inner",
  }
  resolver = GraphResolver(registry)
  with pytest.raises(SnippetExecError):
    exec_python(outer_code, {}, resolver, trusted=True)


def test_context_execute_without_resolver_raises():
  code = "def compute(context):\n  return context.compute('x')"
  with pytest.raises(SnippetExecError) as exc:
    exec_python(code, {})
  assert "resolver" in str(exc.value).lower()
