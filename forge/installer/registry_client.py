import re
import time
from typing import Optional
from packaging.version import Version, InvalidVersion
from forge.installer.http import get_json
from forge.installer.exceptions import (
  SnippetNotFoundError,
  ValidationError,
)

SUPPORTED_SCHEMA_VERSION = "1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TTL_SECONDS = 5 * 60

_cache: dict = {}


def fetch_index(url: str, allow_insecure_schemes: bool = False) -> dict:
  """GET, parse, validate, and cache the registry index.

  allow_insecure_schemes: when True, accept http:// tarball URLs in addition
  to https://. Intended for integration tests against local servers; never
  enable in production.
  """
  cached = _cache.get(url)
  now = time.monotonic()
  if cached is not None:
    expires_at, data = cached
    if expires_at > now:
      return data

  raw = get_json(url)
  _validate_index(raw, allow_insecure_schemes=allow_insecure_schemes)
  _cache[url] = (now + _TTL_SECONDS, raw)
  return raw


def lookup(index: dict, vault_name: str, version: Optional[str] = None) -> dict:
  """Resolve a vault entry. Returns {tarball, sha256, version}."""
  vaults = index.get("vaults", {})
  vault = vaults.get(vault_name)
  if vault is None:
    raise SnippetNotFoundError(f"vault '{vault_name}' not in registry")

  resolved_version = version or vault.get("latest")
  if resolved_version is None:
    raise SnippetNotFoundError(f"vault '{vault_name}' has no 'latest' and no version requested")

  versions = vault.get("versions", {})
  v = versions.get(resolved_version)
  if v is None:
    raise SnippetNotFoundError(f"vault '{vault_name}' version '{resolved_version}' not in registry")

  return {
    "tarball": v["tarball"],
    "sha256": v["sha256"],
    "version": resolved_version,
  }


def clear_cache() -> None:
  _cache.clear()


def _validate_index(raw: dict, allow_insecure_schemes: bool = False) -> None:
  if not isinstance(raw, dict):
    raise ValidationError("registry index is not a JSON object")

  schema = raw.get("schema_version")
  if schema != SUPPORTED_SCHEMA_VERSION:
    raise ValidationError(f"unsupported schema_version: {schema!r} (expected {SUPPORTED_SCHEMA_VERSION!r})")

  vaults = raw.get("vaults")
  if not isinstance(vaults, dict):
    raise ValidationError("'vaults' must be an object")

  for name, vault in vaults.items():
    _validate_vault(name, vault, allow_insecure_schemes=allow_insecure_schemes)


def _validate_vault(name: str, vault: dict, allow_insecure_schemes: bool = False) -> None:
  if not isinstance(vault, dict):
    raise ValidationError(f"vault '{name}' is not an object")

  versions = vault.get("versions")
  if not isinstance(versions, dict) or not versions:
    raise ValidationError(f"vault '{name}' has no versions")

  latest = vault.get("latest")
  if latest is not None and latest not in versions:
    raise ValidationError(f"vault '{name}' latest='{latest}' not present in versions")

  for version_str, version_entry in versions.items():
    _validate_version_key(name, version_str)
    _validate_version_entry(name, version_str, version_entry, allow_insecure_schemes=allow_insecure_schemes)


def _validate_version_key(vault_name: str, version_str: str) -> None:
  try:
    Version(version_str)
  except InvalidVersion as e:
    raise ValidationError(f"vault '{vault_name}' has invalid SemVer key '{version_str}': {e}")


def _validate_version_entry(vault_name: str, version_str: str, entry: dict, allow_insecure_schemes: bool = False) -> None:
  if not isinstance(entry, dict):
    raise ValidationError(f"{vault_name}@{version_str}: entry must be an object")

  tarball = entry.get("tarball")
  allowed_prefixes = ("https://", "http://") if allow_insecure_schemes else ("https://",)
  if not isinstance(tarball, str) or not tarball.startswith(allowed_prefixes):
    expected = "HTTPS" if not allow_insecure_schemes else "HTTPS or HTTP"
    raise ValidationError(f"{vault_name}@{version_str}: tarball must be a {expected} URL")

  sha = entry.get("sha256")
  if not isinstance(sha, str) or not _SHA256_RE.match(sha):
    raise ValidationError(f"{vault_name}@{version_str}: sha256 must be 64-char lowercase hex")
