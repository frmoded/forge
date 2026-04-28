from pathlib import Path

VAULT = str(Path(__file__).parent.parent / "vault")


def test_vec3_print(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "vec3_print",
    "inputs": {"v": [1, 2, 3]},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["type"] == "action"
  assert "1" in data["stdout"]
  assert "2" in data["stdout"]
  assert "3" in data["stdout"]


def test_vec3_add_returns_correct_result(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "vec3_add",
    "inputs": {"a": [1, 2, 3], "b": [4, 5, 6]},
  })
  assert resp.status_code == 200
  data = resp.json()
  assert data["result"] == [5, 7, 9]


def test_vec3_add_prints_result(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "vec3_add",
    "inputs": {"a": [1, 2, 3], "b": [4, 5, 6]},
  })
  assert resp.status_code == 200
  assert "5" in resp.json()["stdout"]
  assert "7" in resp.json()["stdout"]
  assert "9" in resp.json()["stdout"]


def test_vec3_add_zero_vector(client):
  client.post("/connect", json={"vault_path": VAULT})
  resp = client.post("/execute", json={
    "vault_path": VAULT,
    "snippet_id": "vec3_add",
    "inputs": {"a": [1, 2, 3], "b": [0, 0, 0]},
  })
  assert resp.status_code == 200
  assert resp.json()["result"] == [1, 2, 3]
