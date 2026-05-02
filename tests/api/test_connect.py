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
  resp = client.post("/compute", json={
    "vault_path": VAULT,
    "snippet_id": "hello_forge",
    "inputs": {},
  })
  assert resp.status_code == 400


def test_connect_inventory_includes_type_per_snippet(client):
  resp = client.post("/connect", json={"vault_path": VAULT})
  body = resp.json()
  forge_entries = body["snippets"]["forge"]
  assert isinstance(forge_entries, list)
  for entry in forge_entries:
    assert set(entry.keys()) == {"id", "type"}
    assert entry["type"] in ("action", "data", "snapshot")
  authoring_entries = body["snippets"]["authoring"]
  for entry in authoring_entries:
    # Every test-vault snippet is currently action; the shape matters more.
    assert set(entry.keys()) == {"id", "type"}
