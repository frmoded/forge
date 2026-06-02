import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List, Optional

try:
  import tomllib
except ImportError:
  import tomli as tomllib

# v0.3.x: tomli_w, packaging.version, and forge.installer.exceptions
# are not available in the closed-beta Pyodide bundle (tomli_w wasn't
# vendored; packaging likewise; forge.installer is intentionally
# excluded from the bundle scope per the engine-bundle drift filter).
# `read_manifest` is the only function the plugin path exercises; it
# uses ValidationError + a semver check + tomllib. Make all three
# imports lazy/fallback so reads work in Pyodide without breaking
# writes/installs on systems where the full stack is available.

try:
  from forge.installer.exceptions import ValidationError  # type: ignore[import-not-found]
except ImportError:
  class ValidationError(Exception):
    """Local fallback when forge.installer isn't on sys.path (Pyodide
    closed-beta bundle excludes the installer subpackage). Callers that
    catch ValidationError still work via duck-typing on the class
    obtained at runtime — caller's import resolves to the same module
    object as this one."""
    pass


def _semver_validators():
  """Return (Version, InvalidVersion) from packaging.version if
  available, else a regex-based fallback pair with the same shape.

  Lazy because packaging isn't vendored in the closed-beta Pyodide
  bundle; the validation in Pyodide can fall back to a regex check
  without losing the "obviously-bad-version-string" catch."""
  try:
    from packaging.version import Version, InvalidVersion  # type: ignore[import-not-found]
    return Version, InvalidVersion
  except ImportError:
    class _FallbackInvalidVersion(Exception):
      pass
    # Permissive SemVer-ish: <major>.<minor>.<patch>(-prerelease)?(+build)?
    _SEMVER_RE = re.compile(
      r"^\d+(\.\d+){1,2}([-+][0-9A-Za-z.\-+]+)?$"
    )

    class _FallbackVersion:
      def __init__(self, s):
        if not _SEMVER_RE.match(s):
          raise _FallbackInvalidVersion(f"not a valid version: {s!r}")

    return _FallbackVersion, _FallbackInvalidVersion


MANIFEST_FILENAME = "forge.toml"
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


@dataclass(frozen=True)
class Dependency:
  name: str
  version: str


@dataclass(frozen=True)
class Manifest:
  name: str
  version: str
  description: str
  dependencies: List[Dependency] = field(default_factory=list)
  # Domain scoping (constitution B9). None = field absent in forge.toml
  # → interpret as "all registered domains" (back-compat for vaults
  # authored before the field existed; load-time warning). [] = explicit
  # opt-out (core-only: base globals + base prompt only). ["moda", ...] =
  # exactly those domains' injected globals + prompt fragments.
  domains: Optional[List[str]] = None


def read_manifest(vault_dir: Path) -> Manifest:
  path = Path(vault_dir) / MANIFEST_FILENAME
  if not path.is_file():
    raise ValidationError(f"manifest not found at {path}")
  with open(path, "rb") as f:
    raw = tomllib.load(f)
  return _from_dict(raw)


def write_manifest(vault_dir: Path, manifest: Manifest) -> None:
  _validate(manifest)
  # tomli_w is only needed for writes; lazy-import keeps the read path
  # (the only one the closed-beta Pyodide bundle exercises) working
  # without tomli_w being vendored.
  import tomli_w
  path = Path(vault_dir) / MANIFEST_FILENAME
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "wb") as f:
    tomli_w.dump(_to_dict(manifest), f)


def add_or_update_dep(manifest: Manifest, name: str, version: str) -> Manifest:
  """Returns a new Manifest with the dep added or its version updated."""
  new_deps = []
  found = False
  for dep in manifest.dependencies:
    if dep.name == name:
      new_deps.append(Dependency(name=name, version=version))
      found = True
    else:
      new_deps.append(dep)
  if not found:
    new_deps.append(Dependency(name=name, version=version))
  return replace(manifest, dependencies=new_deps)


def _from_dict(raw: dict) -> Manifest:
  for required in ("name", "version", "description"):
    if required not in raw:
      raise ValidationError(f"manifest missing required field: {required}")

  deps_raw = raw.get("dependencies", []) or []
  if not isinstance(deps_raw, list):
    raise ValidationError("'dependencies' must be an array of tables")

  deps: List[Dependency] = []
  for i, entry in enumerate(deps_raw):
    if not isinstance(entry, dict):
      raise ValidationError(f"dependencies[{i}] must be a table")
    if "name" not in entry or "version" not in entry:
      raise ValidationError(f"dependencies[{i}] missing 'name' or 'version'")
    deps.append(Dependency(name=entry["name"], version=entry["version"]))

  # `domains`: absent → None ("all", back-compat); present → must be a
  # list of strings (possibly empty, meaning core-only).
  domains_raw = raw.get("domains", None)
  if domains_raw is not None:
    if not isinstance(domains_raw, list) or not all(
      isinstance(d, str) for d in domains_raw
    ):
      raise ValidationError("'domains' must be a list of strings")

  m = Manifest(
    name=raw["name"],
    version=raw["version"],
    description=raw["description"],
    dependencies=deps,
    domains=domains_raw,
  )
  _validate(m)
  return m


def _to_dict(manifest: Manifest) -> dict:
  out: dict = {
    "name": manifest.name,
    "version": manifest.version,
    "description": manifest.description,
  }
  if manifest.dependencies:
    out["dependencies"] = [{"name": d.name, "version": d.version} for d in manifest.dependencies]
  if manifest.domains is not None:
    out["domains"] = list(manifest.domains)
  return out


def _validate(manifest: Manifest) -> None:
  if not _NAME_RE.match(manifest.name):
    raise ValidationError(
      f"invalid name '{manifest.name}': must be 3-64 chars, lowercase a-z/0-9/'-', start with a letter"
    )
  _validate_semver(manifest.version, "manifest.version")
  if not (1 <= len(manifest.description) <= 200):
    raise ValidationError("description must be 1-200 chars")
  for d in manifest.dependencies:
    if not _NAME_RE.match(d.name):
      raise ValidationError(f"dependency name '{d.name}' has invalid format")
    _validate_semver(d.version, f"dependency '{d.name}' version")


def _validate_semver(s: str, label: str) -> None:
  Version, InvalidVersion = _semver_validators()
  try:
    Version(s)
  except InvalidVersion as e:
    raise ValidationError(f"{label} is not valid SemVer: {e}")
