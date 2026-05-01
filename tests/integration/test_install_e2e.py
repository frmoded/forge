from pathlib import Path

from forge.builtins.loader import load_builtin_vault
from forge.core.executor import extract_python, exec_python
from forge.core.snippet_registry import SnippetRegistry
from forge.core.graph_resolver import GraphResolver
from forge.core.manifest import read_manifest, Dependency

from .conftest import pack_tarball, build_index


# --- fixture content for the published vault ---

_FORGE_CORE_MANIFEST = '''\
name = "forge-core"
version = "0.1.0"
description = "Test fixture vault for end-to-end install."
'''

_HELLO_REGISTRY_MD = '''\
---
type: action
description: Greets the registry.
---

# English

Print "Hello from forge-core" and return the greeting string.

# Python

```python
def compute(context):
  print("Hello from forge-core")
  return "Hello from forge-core"
```
'''


def _resolve_install_snippet():
  snippets = load_builtin_vault()
  install = next(s for s in snippets if s["snippet_id"] == "forge/install")
  return snippets, extract_python(install["body"])


def _setup_published_vault(tmp_path: Path):
  """Stages the on-disk vault that will be packed into a tarball."""
  src = tmp_path / "published-source"
  src.mkdir()
  (src / "forge.toml").write_text(_FORGE_CORE_MANIFEST)
  (src / "hello_registry.md").write_text(_HELLO_REGISTRY_MD)
  return src


def _pack(src_dir: Path, dest_path: Path, version: str = "0.1.0", vault_name: str = "forge-core") -> str:
  entries = []
  for p in src_dir.rglob("*"):
    if p.is_file():
      rel = p.relative_to(src_dir).as_posix()
      entries.append((rel, p.read_text()))
  return pack_tarball(entries, wrapper=f"{vault_name}-{version}", dest_path=dest_path)


def _make_authoring_vault(tmp_path: Path, with_manifest: bool = True) -> Path:
  vault = tmp_path / "authoring-vault"
  vault.mkdir()
  if with_manifest:
    (vault / "forge.toml").write_text(
      'name = "my-test-vault"\nversion = "0.0.0"\ndescription = "Authoring vault under test."\n'
    )
  return vault


def _build_session(authoring_vault: Path):
  registry = SnippetRegistry()
  registry.scan(str(authoring_vault))
  registry.register_builtin_vault(load_builtin_vault())
  return registry, GraphResolver(registry)


def _run_install(*, code: str, registry, resolver, vault_path: Path, vault_name: str, version=None):
  return exec_python(
    code, {"vault_name": vault_name, "version": version},
    resolver,
    vault_path=str(vault_path),
    registry=registry,
    trusted=True,
  )


# ---------- the main e2e test ----------

def test_install_e2e_full_pipeline(tmp_path, monkeypatch, local_registry_server):
  # 1) Build fixture vault on disk.
  published = _setup_published_vault(tmp_path)

  # 2) Pack into a wrapped tarball; record SHA.
  tarball_path = tmp_path / "forge-core-0.1.0.tar.gz"
  sha = _pack(published, tarball_path)

  # 3) Build registry index.
  index = build_index(
    vault_name="forge-core",
    version="0.1.0",
    tarball_url=f"{local_registry_server.url}/forge-core-0.1.0.tar.gz",
    sha=sha,
  )

  # 4) Stand up local HTTP server.
  local_registry_server.add_json("/index.json", index)
  local_registry_server.add_file("/forge-core-0.1.0.tar.gz", tarball_path.read_bytes())

  # 5) Set up authoring vault.
  authoring = _make_authoring_vault(tmp_path, with_manifest=True)

  # 6) Configure Forge to use the local server.
  monkeypatch.setenv("FORGE_REGISTRY_URL", f"{local_registry_server.url}/index.json")
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))

  # 7) Initialize the snippet registry.
  registry, resolver = _build_session(authoring)

  # 8) Run install via the snippet runtime.
  _, install_code = _resolve_install_snippet()
  stdout, result = _run_install(
    code=install_code, registry=registry, resolver=resolver,
    vault_path=authoring, vault_name="forge-core",
  )

  # 9) Verify resulting state.
  installed = authoring / "forge-core"
  assert installed.is_dir(), "vault directory should exist after install"
  assert (installed / "forge.toml").is_file()
  assert (installed / "hello_registry.md").is_file()

  installed_manifest = read_manifest(installed)
  assert installed_manifest.name == "forge-core"
  assert installed_manifest.version == "0.1.0"

  authoring_manifest = read_manifest(authoring)
  assert Dependency(name="forge-core", version="0.1.0") in authoring_manifest.dependencies

  hit = resolver.resolve("forge-core/hello_registry")
  assert hit is not None
  assert hit["vault"] == "forge-core"
  assert hit["source"] == "library"

  cache_path = tmp_path / "cache" / "tarballs" / f"{sha}.tar.gz"
  assert cache_path.is_file()

  assert result["vault_name"] == "forge-core"
  assert result["version"] == "0.1.0"
  assert "[[forge-core/" in result["message"]

  # 10) Run install a second time. Cache hit on tarball — no second download.
  _, result2 = _run_install(
    code=install_code, registry=registry, resolver=resolver,
    vault_path=authoring, vault_name="forge-core",
  )
  assert result2["vault_name"] == "forge-core"
  assert result2["version"] == "0.1.0"
  tarball_hits = local_registry_server.request_counts["/forge-core-0.1.0.tar.gz"]
  assert tarball_hits == 1, f"expected 1 tarball download (cache hit on second install), got {tarball_hits}"


# ---------- additional cases ----------

def test_install_e2e_authoring_vault_without_manifest(tmp_path, monkeypatch, local_registry_server):
  """add_dep auto-creates a manifest when the authoring vault has none."""
  published = _setup_published_vault(tmp_path)
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

  authoring = _make_authoring_vault(tmp_path, with_manifest=False)
  monkeypatch.setenv("FORGE_REGISTRY_URL", f"{local_registry_server.url}/index.json")
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))
  registry, resolver = _build_session(authoring)

  _, install_code = _resolve_install_snippet()
  _run_install(
    code=install_code, registry=registry, resolver=resolver,
    vault_path=authoring, vault_name="forge-core",
  )

  assert (authoring / "forge.toml").is_file()
  m = read_manifest(authoring)
  # default name comes from authoring dir basename ("authoring-vault" — sanitized, valid)
  assert m.version == "0.0.0"
  assert m.description == "Authoring vault."
  assert Dependency(name="forge-core", version="0.1.0") in m.dependencies


def test_install_e2e_resolves_via_qualified_reference(tmp_path, monkeypatch, local_registry_server):
  """ADR 0002: qualified references go directly to the named vault."""
  published = _setup_published_vault(tmp_path)
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

  authoring = _make_authoring_vault(tmp_path, with_manifest=True)
  monkeypatch.setenv("FORGE_REGISTRY_URL", f"{local_registry_server.url}/index.json")
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))
  registry, resolver = _build_session(authoring)

  _, install_code = _resolve_install_snippet()
  _run_install(
    code=install_code, registry=registry, resolver=resolver,
    vault_path=authoring, vault_name="forge-core",
  )

  qualified = resolver.resolve("forge-core/hello_registry")
  assert qualified["snippet_id"] == "forge-core/hello_registry"
  # bare reference resolves the same snippet because authoring has no override
  # and the manifest dep order places forge-core before forge in the search.
  bare = resolver.resolve("hello_registry")
  assert bare["vault"] == "forge-core"
  assert registry.resolution_order() == ["authoring", "forge-core", "forge"]
