import os
import pytest
from fastapi.testclient import TestClient
from forge.api.server import app, states

VAULT = os.path.join(os.path.dirname(__file__), "vault")


@pytest.fixture(autouse=True)
def reset_states():
  states.clear()
  yield
  states.clear()


client = TestClient(app)


def test_connect():
  resp = client.post("/connect", json={"vault_path": VAULT})
  assert resp.status_code == 200
  assert resp.json() == {"status": "connected", "vault_path": VAULT}


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
