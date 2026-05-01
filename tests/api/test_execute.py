# Tests for the /compute endpoint (filename retained for git-history continuity).
from pathlib import Path

VAULT = str(Path(__file__).parent.parent / "vault")


def test_hello_forge_stdout(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/compute", json={
    "vault_path": VAULT,
    "snippet_id": "hello_forge",
    "inputs": {},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["type"] == "action"
  assert "Hello Forge" in data["stdout"]


def test_unknown_snippet_returns_404(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/compute", json={
    "vault_path": VAULT,
    "snippet_id": "does_not_exist",
    "inputs": {},
  })
  assert resp.status_code == 404


def test_greet_with_name(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/compute", json={
    "vault_path": VAULT,
    "snippet_id": "greet",
    "inputs": {"name": "Alice"},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["type"] == "action"
  assert "Hello Alice" in data["stdout"]


def test_hello_world_delegates_to_greet(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/compute", json={
    "vault_path": VAULT,
    "snippet_id": "hello_world",
    "inputs": {},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["type"] == "action"
  assert "Hello world" in data["stdout"]


def test_greet_with_positional_arg(client):
  """Positional args flow as fn(context, *args). [[greet]] "Alice" → hello(context, "Alice")."""
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/compute", json={
    "vault_path": VAULT,
    "snippet_id": "greet",
    "args": ["Alice"],
  })
  assert resp.status_code == 200
  assert "Hello Alice" in resp.json()["stdout"]


def test_mixed_positional_and_named(client):
  """Mixing positional and named: extra position fills the first param, named fills the rest."""
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/compute", json={
    "vault_path": VAULT,
    "snippet_id": "vec3_add",
    "args": [[1, 2, 3]],
    "inputs": {"b": [4, 5, 6]},
  })
  assert resp.status_code == 200
  assert resp.json()["result"] == [5, 7, 9]
