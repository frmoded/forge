import os
import shutil
import pytest
from pathlib import Path
from forge.core.executor import exec_python
from forge.core.snippet_registry import SnippetRegistry
from forge.core.graph_resolver import GraphResolver

PARTIAL_VAULT_SRC = Path(__file__).parent.parent / "vault_partial"

requires_llm = pytest.mark.skipif(
  not os.environ.get("ANTHROPIC_API_KEY"),
  reason="ANTHROPIC_API_KEY not set",
)


@pytest.fixture
def partial_vault(tmp_path):
  """Fresh copy of vault_partial per test — cleaned up automatically."""
  dst = tmp_path / "vault_partial"
  shutil.copytree(PARTIAL_VAULT_SRC, dst)
  return str(dst)


# --- error cases (no LLM required) ---

def test_generate_without_connect_returns_400(client):
  resp = client.post("/generate", json={
    "vault_path": "/nonexistent/vault",
    "snippet_id": "anything",
  })
  assert resp.status_code == 400


def test_generate_unknown_snippet_returns_404(client, partial_vault):
  client.post("/connect", json={"vault_path": partial_vault})
  resp = client.post("/generate", json={
    "vault_path": partial_vault,
    "snippet_id": "does_not_exist",
  })
  assert resp.status_code == 404


def test_generate_response_shape(client, partial_vault):
  client.post("/connect", json={"vault_path": partial_vault})
  resp = client.post("/generate", json={
    "vault_path": partial_vault,
    "snippet_id": "does_not_exist",
  })
  # shape check on error path
  assert "detail" in resp.json()


# --- LLM tests ---

@requires_llm
def test_generate_hello_forge_produces_working_code(client, partial_vault):
  client.post("/connect", json={"vault_path": partial_vault})
  resp = client.post("/generate", json={
    "vault_path": partial_vault,
    "snippet_id": "partial_hello_forge",
  })
  assert resp.status_code == 200
  generated_code = resp.json()["generated"]["partial_hello_forge"]
  assert generated_code

  stdout, _ = exec_python(generated_code, {})
  assert "Hello Forge" in stdout


@requires_llm
def test_generate_non_recursive_only_generates_requested_snippet(client, partial_vault):
  client.post("/connect", json={"vault_path": partial_vault})
  resp = client.post("/generate", json={
    "vault_path": partial_vault,
    "snippet_id": "partial_hello_world",
    "recursive": False,
  })
  assert resp.status_code == 200
  generated = resp.json()["generated"]
  assert "partial_hello_world" in generated
  assert "partial_greet" not in generated


@requires_llm
def test_generate_hello_world_recursive_executes_full_chain(client, partial_vault):
  client.post("/connect", json={"vault_path": partial_vault})
  resp = client.post("/generate", json={
    "vault_path": partial_vault,
    "snippet_id": "partial_hello_world",
    "recursive": True,
  })
  assert resp.status_code == 200
  generated = resp.json()["generated"]
  assert "partial_hello_world" in generated
  assert "partial_greet" in generated

  registry = SnippetRegistry()
  registry._vaults.setdefault("authoring", {})
  for sid, code in generated.items():
    registry._vaults["authoring"][sid] = {
      "meta": {"type": "action"},
      "body": f"# Python\n\n```python\n{code}\n```",
      "path": "",
      "vault": "authoring",
      "source": "authoring",
      "snippet_id": f"authoring/{sid}",
    }
  resolver = GraphResolver(registry)

  stdout, _ = exec_python(generated["partial_hello_world"], {}, resolver)
  assert "Hello world" in stdout


@requires_llm
def test_generate_random_range_returns_value_within_bounds(client, partial_vault):
  client.post("/connect", json={"vault_path": partial_vault})
  resp = client.post("/generate", json={
    "vault_path": partial_vault,
    "snippet_id": "partial_random_range",
  })
  assert resp.status_code == 200
  generated_code = resp.json()["generated"]["partial_random_range"]
  assert generated_code

  for _ in range(10):
    _, result = exec_python(generated_code, {"min": 1, "max": 10})
    assert isinstance(result, int), f"expected int, got {type(result).__name__}: {result}"
    assert 1 <= result <= 10, f"result {result} out of range [1, 10]"
