"""Phase 4 tests: /freeze endpoint."""
from forge.core.snapshots import write_snapshot, read_snapshot


def test_freeze_flips_state_on_existing_snapshot(client, tmp_path):
  """Pre-write a live snapshot, then POST /freeze with state=frozen."""
  write_snapshot(str(tmp_path), "authoring/a", "authoring/b", value=42)
  resp = client.post("/freeze", json={
    "vault_path": str(tmp_path),
    "caller": "authoring/a",
    "callee": "authoring/b",
    "state": "frozen",
  })
  assert resp.status_code == 200
  assert resp.json() == {"caller": "authoring/a", "callee": "authoring/b", "state": "frozen"}

  snap = read_snapshot(str(tmp_path), "authoring/a", "authoring/b")
  assert snap["meta"]["state"] == "frozen"


def test_unfreeze_flips_back_to_live(client, tmp_path):
  write_snapshot(str(tmp_path), "authoring/a", "authoring/b", value=42)
  client.post("/freeze", json={
    "vault_path": str(tmp_path),
    "caller": "authoring/a",
    "callee": "authoring/b",
    "state": "frozen",
  })
  resp = client.post("/freeze", json={
    "vault_path": str(tmp_path),
    "caller": "authoring/a",
    "callee": "authoring/b",
    "state": "live",
  })
  assert resp.status_code == 200
  snap = read_snapshot(str(tmp_path), "authoring/a", "authoring/b")
  assert snap["meta"]["state"] == "live"


def test_freeze_404_when_edge_never_traversed(client, tmp_path):
  resp = client.post("/freeze", json={
    "vault_path": str(tmp_path),
    "caller": "authoring/a",
    "callee": "authoring/b",
    "state": "frozen",
  })
  assert resp.status_code == 404
  assert "never been traversed" in resp.json()["detail"]


def test_freeze_422_on_invalid_state(client, tmp_path):
  write_snapshot(str(tmp_path), "authoring/a", "authoring/b", value=42)
  resp = client.post("/freeze", json={
    "vault_path": str(tmp_path),
    "caller": "authoring/a",
    "callee": "authoring/b",
    "state": "thawed",
  })
  assert resp.status_code == 422


def test_freeze_then_compute_respects_state(client, tmp_path):
  """End-to-end: connect, run, freeze, mutate callee, run again, expect frozen value."""
  # Set up a real authoring vault on disk with two snippets.
  (tmp_path / "outer.md").write_text("""---
type: action
---
# English
calls inner

# Python

```python
def compute(context):
  return context.compute('inner')
```
""")
  (tmp_path / "inner.md").write_text("""---
type: action
---
# English
returns v1

# Python

```python
def compute(context):
  return 'v1'
```
""")

  client.post("/connect", json={"vault_path": str(tmp_path)})
  resp = client.post("/compute", json={
    "vault_path": str(tmp_path), "snippet_id": "outer", "inputs": {},
  })
  assert resp.json()["result"] == "v1"

  # Freeze the edge.
  client.post("/freeze", json={
    "vault_path": str(tmp_path),
    "caller": "authoring/outer",
    "callee": "authoring/inner",
    "state": "frozen",
  })

  # Mutate inner.md so a fresh compute would return v2; the freeze should hold v1.
  (tmp_path / "inner.md").write_text("""---
type: action
---
# Python

```python
def compute(context):
  return 'v2'
```
""")
  client.post("/connect", json={"vault_path": str(tmp_path), "force": True})
  resp = client.post("/compute", json={
    "vault_path": str(tmp_path), "snippet_id": "outer", "inputs": {},
  })
  assert resp.json()["result"] == "v1"  # frozen pin
