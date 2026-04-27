from pathlib import Path

VAULT = str(Path(__file__).parent.parent / "vault")


def test_hello_forge_stdout(client):
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


def test_unknown_snippet_returns_404(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "does_not_exist",
    "kwargs": {},
  })
  assert resp.status_code == 404


def test_greet_with_name(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "greet",
    "kwargs": {"name": "Alice"},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["type"] == "action"
  assert "Hello Alice" in data["stdout"]


def test_hello_world_delegates_to_greet(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "hello_world",
    "kwargs": {},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["type"] == "action"
  assert "Hello world" in data["stdout"]
