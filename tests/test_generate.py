import os
import pytest
from fastapi.testclient import TestClient
from forge.api.server import app, get_session_manager, VaultSessionManager
from forge.core.executor import exec_python

PARTIAL_VAULT = os.path.join(os.path.dirname(__file__), "vault_partial")

_test_manager = VaultSessionManager()

pytestmark = pytest.mark.skipif(
  not os.environ.get("ANTHROPIC_API_KEY"),
  reason="ANTHROPIC_API_KEY not set",
)


@pytest.fixture(autouse=True)
def reset_manager():
  _test_manager.clear()
  app.dependency_overrides[get_session_manager] = lambda: _test_manager
  yield
  _test_manager.clear()
  app.dependency_overrides.clear()


client = TestClient(app)


def test_generate_hello_forge_produces_working_code():
  client.post("/connect", json={"vault_path": PARTIAL_VAULT})

  resp = client.post("/generate", json={
    "vault_path": PARTIAL_VAULT,
    "snippet_id": "partial_hello_forge",
  })
  assert resp.status_code == 200
  data = resp.json()
  assert "partial_hello_forge" in data["generated"]

  generated_code = data["generated"]["partial_hello_forge"]
  assert generated_code, "LLM returned empty code"

  stdout, _ = exec_python(generated_code, {})
  assert "Hello Forge" in stdout
