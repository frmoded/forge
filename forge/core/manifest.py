import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List
import tomli_w
from packaging.version import Version, InvalidVersion
from forge.installer.exceptions import ValidationError

try:
  import tomllib
except ImportError:
  import tomli as tomllib

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


def read_manifest(vault_dir: Path) -> Manifest:
  path = Path(vault_dir) / MANIFEST_FILENAME
  if not path.is_file():
    raise ValidationError(f"manifest not found at {path}")
  with open(path, "rb") as f:
    raw = tomllib.load(f)
  return _from_dict(raw)


def write_manifest(vault_dir: Path, manifest: Manifest) -> None:
  _validate(manifest)
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

  m = Manifest(
    name=raw["name"],
    version=raw["version"],
    description=raw["description"],
    dependencies=deps,
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
  try:
    Version(s)
  except InvalidVersion as e:
    raise ValidationError(f"{label} is not valid SemVer: {e}")
