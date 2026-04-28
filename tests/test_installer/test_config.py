from pathlib import Path
from forge.config import get_config, DEFAULT_REGISTRY_URL, DEFAULT_CACHE_DIR


def test_defaults_when_env_unset(monkeypatch, tmp_path):
  monkeypatch.delenv("FORGE_REGISTRY_URL", raising=False)
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))
  cfg = get_config()
  assert cfg.registry_url == DEFAULT_REGISTRY_URL


def test_env_overrides(monkeypatch, tmp_path):
  monkeypatch.setenv("FORGE_REGISTRY_URL", "https://example.com/index.json")
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))
  cfg = get_config()
  assert cfg.registry_url == "https://example.com/index.json"
  assert cfg.cache_dir == tmp_path / "cache"


def test_cache_dir_created_if_missing(monkeypatch, tmp_path):
  cache_dir = tmp_path / "fresh-cache"
  monkeypatch.setenv("FORGE_CACHE_DIR", str(cache_dir))
  assert not cache_dir.exists()
  cfg = get_config()
  assert cfg.cache_dir.exists()
  assert cfg.cache_dir.is_dir()


def test_default_cache_dir_is_under_home():
  assert DEFAULT_CACHE_DIR == Path.home() / ".cache" / "forge"


def test_config_is_frozen(monkeypatch, tmp_path):
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "c"))
  cfg = get_config()
  import pytest
  with pytest.raises(Exception):
    cfg.registry_url = "x"  # type: ignore
