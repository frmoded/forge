from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from forge.api.server import app, get_session_manager, VaultSessionManager

from .conftest import pack_tarball, build_index


_FORGE_CORE_MANIFEST = '''\
name = "forge-core"
version = "0.1.0"
description = "Test fixture vault for end-to-end install via the HTTP API."
'''

_HELLO_REGISTRY_MD = '''\
---
type: action
description: Greets the registry.
---

# English

Print and return "hello registry".

# Python

```python
def compute(context):
  print("hello registry")
  return "hello registry"
```
'''


@pytest.fixture
def isolated_manager():
  """Each test gets a fresh VaultSessionManager so server-level state doesn't leak."""
  m = VaultSessionManager()
  app.dependency_overrides[get_session_manager] = lambda: m
  yield m
  m.clear()
  app.dependency_overrides.clear()


@pytest.fixture
def api_client(isolated_manager):
  return TestClient(app)


def _stage_published_vault(tmp_path: Path):
  src = tmp_path / "published-source"
  src.mkdir()
  (src / "forge.toml").write_text(_FORGE_CORE_MANIFEST)
  (src / "hello_registry.md").write_text(_HELLO_REGISTRY_MD)
  return src


def _pack(src_dir: Path, dest: Path, version: str = "0.1.0", vault_name: str = "forge-core") -> str:
  entries = []
  for p in src_dir.rglob("*"):
    if p.is_file():
      rel = p.relative_to(src_dir).as_posix()
      entries.append((rel, p.read_text()))
  return pack_tarball(entries, wrapper=f"{vault_name}-{version}", dest_path=dest)


def test_install_via_api_full_flow(tmp_path, monkeypatch, local_registry_server, api_client):
  # 1) Stand up the local registry server (fixture).
  published = _stage_published_vault(tmp_path)
  tarball_path = tmp_path / "forge-core-0.1.0.tar.gz"
  sha = _pack(published, tarball_path)

  index = build_index(
    vault_name="forge-core",
    version="0.1.0",
    tarball_url=f"{local_registry_server.url}/forge-core-0.1.0.tar.gz",
    sha=sha,
  )
  local_registry_server.add_json("/index.json", index)
  local_registry_server.add_file("/forge-core-0.1.0.tar.gz", tarball_path.read_bytes())

  # 2) The TestClient is the api_client fixture above.

  # 3) Set up the authoring vault and configure Forge.
  authoring = tmp_path / "authoring"
  authoring.mkdir()
  (authoring / "forge.toml").write_text(
    'name = "my-test-vault"\nversion = "0.0.0"\ndescription = "Authoring vault under HTTP install test."\n'
  )
  monkeypatch.setenv("FORGE_REGISTRY_URL", f"{local_registry_server.url}/index.json")
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))

  # 4) POST /connect with the authoring vault.
  resp = api_client.post("/connect", json={"vault_path": str(authoring)})
  assert resp.status_code == 200
  body = resp.json()
  assert body["status"] == "connected"
  assert "snippets" in body
  # Built-ins are always present after connect; forge-core is not yet installed.
  assert "forge/install" not in body["snippets"]  # bare_ids per vault, not qualified
  assert {"id": "install", "type": "action"} in body["snippets"]["forge"]
  assert "forge-core" not in body["snippets"]

  # 5) POST /compute install.
  resp = api_client.post("/compute", json={
    "vault_path": str(authoring),
    "snippet_id": "install",
    "inputs": {"vault_name": "forge-core"},
  })
  assert resp.status_code == 200, resp.text
  payload = resp.json()
  assert payload["type"] == "action"
  result = payload["result"]
  assert result["vault_name"] == "forge-core"
  assert result["version"] == "0.1.0"
  assert "[[forge-core/" in result["message"]

  # 6) POST /connect again to refresh the inventory view.
  resp = api_client.post("/connect", json={"vault_path": str(authoring)})
  assert resp.status_code == 200
  body = resp.json()

  # 7) Inventory now includes the installed library vault.
  assert "forge-core" in body["snippets"]
  assert {"id": "hello_registry", "type": "action"} in body["snippets"]["forge-core"]

  # 8) POST /compute the new vault's snippet via qualified reference.
  resp = api_client.post("/compute", json={
    "vault_path": str(authoring),
    "snippet_id": "forge-core/hello_registry",
    "inputs": {},
  })
  assert resp.status_code == 200, resp.text
  payload = resp.json()

  # 9) The hello_registry snippet ran.
  assert payload["type"] == "action"
  assert payload["result"] == "hello registry"
  assert "hello registry" in payload["stdout"]


def test_install_via_api_propagates_failure(tmp_path, monkeypatch, local_registry_server, api_client):
  """When install fails (registry unreachable / bad SHA), the API returns a structured error."""
  published = _stage_published_vault(tmp_path)
  tarball_path = tmp_path / "forge-core-0.1.0.tar.gz"
  _pack(published, tarball_path)

  # Index claims a SHA that doesn't match the tarball — install should fail at verify_sha256.
  index = build_index(
    vault_name="forge-core",
    version="0.1.0",
    tarball_url=f"{local_registry_server.url}/forge-core-0.1.0.tar.gz",
    sha="0" * 64,
  )
  local_registry_server.add_json("/index.json", index)
  local_registry_server.add_file("/forge-core-0.1.0.tar.gz", tarball_path.read_bytes())

  authoring = tmp_path / "authoring"
  authoring.mkdir()
  (authoring / "forge.toml").write_text(
    'name = "my-test-vault"\nversion = "0.0.0"\ndescription = "x."\n'
  )
  monkeypatch.setenv("FORGE_REGISTRY_URL", f"{local_registry_server.url}/index.json")
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))

  api_client.post("/connect", json={"vault_path": str(authoring)})
  resp = api_client.post("/compute", json={
    "vault_path": str(authoring),
    "snippet_id": "install",
    "inputs": {"vault_name": "forge-core"},
  })
  assert resp.status_code == 422
  detail = resp.json()["detail"]
  assert "error" in detail
  assert "stdout" in detail
  assert "hash mismatch" in detail["error"].lower() or "0000" in detail["error"]
