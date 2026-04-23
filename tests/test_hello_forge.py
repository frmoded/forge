import os
import pytest
from fastapi.testclient import TestClient
from forge.api.server import app, get_session_manager, VaultSessionManager

VAULT = os.path.join(os.path.dirname(__file__), "vault")

_test_manager = VaultSessionManager()


@pytest.fixture(autouse=True)
def reset_manager():
  _test_manager.clear()
  app.dependency_overrides[get_session_manager] = lambda: _test_manager
  yield
  _test_manager.clear()
  app.dependency_overrides.clear()


client = TestClient(app)


def test_connect():
  resp = client.post("/connect", json={"vault_path": VAULT})
  assert resp.status_code == 200
  body = resp.json()
  assert body["status"] == "connected"
  assert body["vault_path"] == VAULT
  assert body["warnings"] == []


def test_hello_forge_stdout():
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "hello_forge",
    "kwargs": {},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["type"] == "action"
  assert "Hello Forge" in data["stdout"]


def test_connect_force_reloads():
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/connect", json={"vault_path": VAULT, "force": True})
  assert resp.status_code == 200
  assert resp.json()["status"] == "connected"


def test_hello_forge_unknown_snippet():
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "does_not_exist",
    "kwargs": {},
  })
  assert resp.status_code == 404


def test_execute_without_connect():
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "hello_forge",
    "kwargs": {},
  })
  assert resp.status_code == 400
