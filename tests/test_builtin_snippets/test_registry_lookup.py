from unittest.mock import patch


_INDEX = {
  "schema_version": "1",
  "vaults": {
    "forge-core": {
      "latest": "0.2.0",
      "versions": {
        "0.1.0": {"tarball": "https://example.com/v0.1.0.tar.gz", "sha256": "a" * 64},
        "0.2.0": {"tarball": "https://example.com/v0.2.0.tar.gz", "sha256": "b" * 64},
      },
    }
  },
}


def test_lookup_returns_latest_when_version_omitted(run_builtin):
  with patch("forge.installer.registry_client.fetch_index", return_value=_INDEX):
    _, result = run_builtin("forge/registry/lookup", vault_name="forge-core")
  assert result["version"] == "0.2.0"
  assert result["tarball"] == "https://example.com/v0.2.0.tar.gz"
  assert result["sha256"] == "b" * 64


def test_lookup_returns_specific_version(run_builtin):
  with patch("forge.installer.registry_client.fetch_index", return_value=_INDEX):
    _, result = run_builtin("forge/registry/lookup", vault_name="forge-core", version="0.1.0")
  assert result["version"] == "0.1.0"
  assert result["tarball"].endswith("v0.1.0.tar.gz")


def test_lookup_uses_config_registry_url(run_builtin, monkeypatch, tmp_path):
  monkeypatch.setenv("FORGE_REGISTRY_URL", "https://my-registry.example/index.json")
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path))
  seen_url = {}

  def _capture(url):
    seen_url["url"] = url
    return _INDEX

  with patch("forge.installer.registry_client.fetch_index", side_effect=_capture):
    run_builtin("forge/registry/lookup", vault_name="forge-core")
  assert seen_url["url"] == "https://my-registry.example/index.json"


def test_lookup_unknown_vault_raises(run_builtin):
  from forge.core.executor import SnippetExecError
  import pytest
  with patch("forge.installer.registry_client.fetch_index", return_value=_INDEX):
    with pytest.raises(SnippetExecError):
      run_builtin("forge/registry/lookup", vault_name="nonexistent")
