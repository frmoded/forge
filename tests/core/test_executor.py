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


def test_exec_python_permits_import():
  # Per constitution B2, snippets get full Python power, including imports.
  code = "def compute(context):\n  import os\n  return os.path.sep"
  _, result = exec_python(code, {})
  assert result in ("/", "\\")


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


def test_untrusted_permits_import():
  # Per constitution B2, snippets get full Python power, including imports.
  # The `trusted` parameter no longer gates builtins exposure.
  code = "def compute(context):\n  import os\n  return os.path.sep"
  _, result = exec_python(code, {}, trusted=False)
  assert result in ("/", "\\")


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


def test_nested_execute_permits_import_in_inner():
  from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
  from forge.core.graph_resolver import GraphResolver

  # Per constitution B2, nested user-authored snippets get full Python power
  # too — imports work regardless of how the parent was invoked.
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
  _, result = exec_python(outer_code, {}, resolver, trusted=True)
  assert result in ("/", "\\")


def test_context_execute_without_resolver_raises():
  code = "def compute(context):\n  return context.compute('x')"
  with pytest.raises(SnippetExecError) as exc:
    exec_python(code, {})
  assert "resolver" in str(exc.value).lower()


def test_v0132_exec_python_raises_clear_error_on_empty_code():
  """v0.2.132 — empty Python facet (the v0.2.131 cohort smoke crash
  mode: mangled English → transpile failed → empty code → compile()
  TypeError).

  Engine must raise SnippetExecError with a user-friendly message
  pointing at the likely cause, not crash at compile() with an
  opaque TypeError about non-string args.
  """
  from forge.core.executor import exec_python, SnippetExecError
  import pytest
  with pytest.raises(SnippetExecError) as exc_info:
    exec_python('', inputs={}, snippet_id='forge-tutorial/01-hello/hello_world')
  msg = str(exc_info.value)
  assert 'Empty or missing Python code' in msg
  assert 'hello_world' in msg
  # Cohort UX: message should hint at the cause + remedy.
  assert 'transpilation failed' in msg or 'English facet' in msg


def test_v0132_exec_python_raises_on_none_code():
  """v0.2.132 — same guard for None (the actual driver smoke shape
  where resolve_action_code returned None and the JS bridge
  passed it through to compile()).
  """
  from forge.core.executor import exec_python, SnippetExecError
  import pytest
  with pytest.raises(SnippetExecError) as exc_info:
    exec_python(None, inputs={}, snippet_id='foo/bar')
  assert 'Empty or missing Python code' in str(exc_info.value)


def test_v0132_exec_python_raises_on_whitespace_only_code():
  """v0.2.132 — whitespace-only code is functionally empty (compile()
  would succeed but execute nothing useful and produce no
  _find_entrypoint hit). Treat as empty for clarity."""
  from forge.core.executor import exec_python, SnippetExecError
  import pytest
  with pytest.raises(SnippetExecError) as exc_info:
    exec_python('   \n\n\t  \n', inputs={}, snippet_id='foo')
  assert 'Empty or missing Python code' in str(exc_info.value)
