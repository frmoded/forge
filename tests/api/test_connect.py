from pathlib import Path

VAULT = str(Path(__file__).parent.parent / "vault")


def test_connect(client):
  resp = client.post("/connect", json={"vault_path": VAULT})
  assert resp.status_code == 200
  body = resp.json()
  assert body["status"] == "connected"
  assert body["vault_path"] == VAULT
  assert body["warnings"] == []


def test_connect_is_idempotent(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/connect", json={"vault_path": VAULT})
  assert resp.status_code == 200
  assert resp.json()["status"] == "connected"


def test_connect_force_reloads(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/connect", json={"vault_path": VAULT, "force": True})
  assert resp.status_code == 200
  assert resp.json()["status"] == "connected"


def test_execute_without_connect_returns_400(client):
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "hello_forge",
    "inputs": {},
  })
  assert resp.status_code == 400
