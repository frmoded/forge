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


# --- Anthropic-error translation (no real LLM call) ---
#
# The /generate handler narrowly caught KeyError → 404 and
# RuntimeError → 500; anthropic SDK exceptions (OverloadedError 529,
# RateLimitError 429, APIConnectionError, AuthenticationError, …) fell
# through to FastAPI's default 500 handler and surfaced to the plugin
# as a bare "Internal Server Error" with no structured detail. The
# new translator maps anthropic.APIError subclasses to:
#   retryable (upstream 5xx, 429, connection/timeout) → 503
#   non-retryable (upstream 4xx) → 502
# both with a structured detail body the plugin can parse to decide
# whether to retry / what Notice to render.

def test_generate_overloaded_error_returns_503_retryable(
  client, partial_vault, monkeypatch,
):
  """529 Overloaded — the exact case the user hit. The SDK keeps
  OverloadedError in `anthropic._exceptions` (not the public
  surface), so we drive the translator via the public APIStatusError
  base class with status_code=529 — same translation logic fires."""
  client.post("/connect", json={"vault_path": partial_vault})

  def boom(*args, **kwargs):
    raise _FakeOverloadedError()

  monkeypatch.setattr(
    "forge.api.server.generate_snippet_code", boom)

  resp = client.post("/generate", json={
    "vault_path": partial_vault,
    "snippet_id": "hello_forge",
  })
  assert resp.status_code == 503
  detail = resp.json()["detail"]
  assert detail["retryable"] is True
  assert detail["upstream_status"] == 529
  assert detail["kind"] == "_FakeOverloadedError"
  assert "Anthropic API:" in detail["error"]


def test_generate_rate_limit_returns_503_retryable(
  client, partial_vault, monkeypatch,
):
  """429 → retryable. Same logic, different upstream status."""
  client.post("/connect", json={"vault_path": partial_vault})
  from anthropic import RateLimitError

  def boom(*args, **kwargs):
    raise RateLimitError(
      message="rate limited",
      response=_FakeResponse(status_code=429),
      body={"type": "error", "error": {"type": "rate_limit_error"}},
    )

  monkeypatch.setattr("forge.api.server.generate_snippet_code", boom)
  resp = client.post("/generate", json={
    "vault_path": partial_vault, "snippet_id": "hello_forge",
  })
  assert resp.status_code == 503
  detail = resp.json()["detail"]
  assert detail["retryable"] is True
  assert detail["upstream_status"] == 429
  assert detail["kind"] == "RateLimitError"


def test_generate_authentication_returns_502_non_retryable(
  client, partial_vault, monkeypatch,
):
  """401 / auth — bad API key. NOT retryable: user has to fix the
  env / config before another try will work. 502 communicates
  'upstream said no' distinct from 'upstream is sick' (503)."""
  client.post("/connect", json={"vault_path": partial_vault})
  from anthropic import AuthenticationError

  def boom(*args, **kwargs):
    raise AuthenticationError(
      message="bad api key",
      response=_FakeResponse(status_code=401),
      body={"type": "error", "error": {"type": "authentication_error"}},
    )

  monkeypatch.setattr("forge.api.server.generate_snippet_code", boom)
  resp = client.post("/generate", json={
    "vault_path": partial_vault, "snippet_id": "hello_forge",
  })
  assert resp.status_code == 502
  detail = resp.json()["detail"]
  assert detail["retryable"] is False
  assert detail["upstream_status"] == 401
  assert detail["kind"] == "AuthenticationError"


def test_generate_connection_error_returns_503_retryable(
  client, partial_vault, monkeypatch,
):
  """Connection / timeout — no upstream status at all. Always
  retryable. upstream_status is None so the plugin can disambiguate
  these from real upstream HTTP failures if it wants to."""
  client.post("/connect", json={"vault_path": partial_vault})
  from anthropic import APIConnectionError

  def boom(*args, **kwargs):
    raise APIConnectionError(request=_FakeRequest())

  monkeypatch.setattr("forge.api.server.generate_snippet_code", boom)
  resp = client.post("/generate", json={
    "vault_path": partial_vault, "snippet_id": "hello_forge",
  })
  assert resp.status_code == 503
  detail = resp.json()["detail"]
  assert detail["retryable"] is True
  assert detail["upstream_status"] is None


# Public-API-only stand-in for the OverloadedError the SDK keeps in
# its private _exceptions module. The translator only branches on
# isinstance(exc, APIError) + exc.status_code, so a public-subclass
# with the right status_code reproduces the production behavior.
from anthropic import APIError as _APIError


class _FakeOverloadedError(_APIError):
  def __init__(self):
    self.message = "Overloaded"
    self.status_code = 529
    self.response = _FakeResponse(status_code=529)
    self.body = {"type": "error", "error": {"type": "overloaded_error"}}
    self.request_id = "req_test"

  def __str__(self) -> str:
    return f"Error code: {self.status_code} - {self.body}"


# Lightweight stand-ins for httpx Response / Request. The Anthropic
# SDK only reads `.status_code` off the response for our purposes,
# and `.method` / `.url` off the request for error formatting.
class _FakeResponse:
  def __init__(self, status_code: int):
    self.status_code = status_code
    self.headers = {}
    self.request = _FakeRequest()


class _FakeRequest:
  method = "POST"
  url = "https://api.anthropic.com/v1/messages"


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
