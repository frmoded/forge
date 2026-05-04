"""Phase 3 tests for /sync_dependencies."""
from pathlib import Path


def _write_snippet(tmp_path: Path, name: str, frontmatter: str, body: str) -> Path:
  path = tmp_path / f"{name}.md"
  path.write_text(f"---\n{frontmatter}\n---\n\n{body}")
  return path


def test_sync_writes_section_for_python_with_calls(client, tmp_path):
  _write_snippet(
    tmp_path, "caller", "type: action",
    "# Python\n\n```python\n"
    "def compute(context):\n"
    "  v = context.compute('callee')\n"
    "  return v\n"
    "```\n",
  )
  client.post("/connect", json={"vault_path": str(tmp_path)})
  resp = client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "caller"})
  assert resp.status_code == 200, resp.text
  body = resp.json()
  assert body["snippet_id"] == "caller"
  assert body["dependencies"] == ["callee"]

  written = (tmp_path / "caller.md").read_text()
  assert "# Dependencies" in written
  assert "[[callee]]" in written


def test_sync_with_no_calls_removes_existing_section(client, tmp_path):
  _write_snippet(
    tmp_path, "lonely", "type: action",
    "# Python\n\n```python\n"
    "def compute(context):\n  return 1\n"
    "```\n\n"
    "# Dependencies\n\n*old note*\n\n[[stale]]\n",
  )
  client.post("/connect", json={"vault_path": str(tmp_path)})
  resp = client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "lonely"})
  assert resp.status_code == 200
  assert resp.json()["dependencies"] == []
  written = (tmp_path / "lonely.md").read_text()
  assert "# Dependencies" not in written
  assert "[[stale]]" not in written


def test_sync_replaces_outdated_section(client, tmp_path):
  _write_snippet(
    tmp_path, "evolving", "type: action",
    "# Python\n\n```python\n"
    "def compute(context):\n"
    "  a = context.compute('alpha')\n"
    "  b = context.compute('beta')\n"
    "  return [a, b]\n"
    "```\n\n"
    "# Dependencies\n\n*outdated*\n\n[[old_only]]\n",
  )
  client.post("/connect", json={"vault_path": str(tmp_path)})
  resp = client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "evolving"})
  assert resp.status_code == 200
  assert resp.json()["dependencies"] == ["alpha", "beta"]
  written = (tmp_path / "evolving.md").read_text()
  assert written.count("# Dependencies") == 1
  assert "[[alpha]]" in written and "[[beta]]" in written
  assert "[[old_only]]" not in written


def test_sync_404_when_snippet_missing(client, tmp_path):
  (tmp_path / "x.md").write_text("---\ntype: action\n---\n\n# Python\n\n```python\ndef compute(context): return 1\n```\n")
  client.post("/connect", json={"vault_path": str(tmp_path)})
  resp = client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "no_such_snippet"})
  assert resp.status_code == 404


def test_sync_422_for_data_snippet(client, tmp_path):
  _write_snippet(
    tmp_path, "the_data", "type: data\ncontent_type: json",
    '"some payload"\n',
  )
  client.post("/connect", json={"vault_path": str(tmp_path)})
  resp = client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "the_data"})
  assert resp.status_code == 422
  assert "Python facet" in resp.json()["detail"]


def test_sync_400_when_vault_not_connected(client, tmp_path):
  resp = client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "any"})
  assert resp.status_code == 400


def test_sync_idempotent(client, tmp_path):
  _write_snippet(
    tmp_path, "stable", "type: action",
    "# Python\n\n```python\ndef compute(context):\n  return context.compute('alpha')\n```\n",
  )
  client.post("/connect", json={"vault_path": str(tmp_path)})
  client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "stable"})
  first = (tmp_path / "stable.md").read_text()
  client.post("/sync_dependencies", json={"vault_path": str(tmp_path), "snippet_id": "stable"})
  second = (tmp_path / "stable.md").read_text()
  assert first == second
