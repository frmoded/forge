import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/frmoded/forge-registry/main/index.json"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "forge"


@dataclass(frozen=True)
class ForgeConfig:
  registry_url: str
  cache_dir: Path


def get_config() -> ForgeConfig:
  registry_url = os.environ.get("FORGE_REGISTRY_URL", DEFAULT_REGISTRY_URL)
  cache_dir = Path(os.environ.get("FORGE_CACHE_DIR", str(DEFAULT_CACHE_DIR)))
  cache_dir.mkdir(parents=True, exist_ok=True)
  return ForgeConfig(registry_url=registry_url, cache_dir=cache_dir)
