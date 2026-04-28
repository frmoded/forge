import os
import tarfile
from pathlib import Path
from forge.installer.exceptions import PathTraversalError


def extract_tarball(tarball_path: Path, target_dir: Path, strip_components: int = 1) -> Path:
  """Extract a .tar.gz, stripping leading path components, rejecting unsafe paths.

  Returns the extraction root (target_dir).
  """
  target_dir = Path(target_dir)
  target_dir.mkdir(parents=True, exist_ok=True)

  with tarfile.open(tarball_path, "r:gz") as tar:
    members = tar.getmembers()

    # validate every entry up front; abort the whole extraction on any unsafe path
    for m in members:
      _validate_member(m.name)
      if m.islnk() or m.issym():
        _validate_member(m.linkname)

    for m in members:
      stripped = _strip_components(m.name, strip_components)
      if stripped is None:
        continue
      _ensure_within(target_dir, target_dir / stripped)
      m.name = stripped
      tar.extract(m, path=target_dir)

  return target_dir


def _validate_member(name: str) -> None:
  if not name:
    return
  if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
    raise PathTraversalError(f"absolute path in tarball: {name}")
  parts = name.replace("\\", "/").split("/")
  if any(p == ".." for p in parts):
    raise PathTraversalError(f"'..' segment in tarball entry: {name}")


def _strip_components(name: str, n: int):
  if n <= 0:
    return name
  parts = name.split("/")
  if len(parts) <= n:
    return None
  return "/".join(parts[n:])


def _ensure_within(root: Path, candidate: Path) -> None:
  root_resolved = os.path.realpath(root)
  cand_resolved = os.path.realpath(candidate)
  if not (cand_resolved == root_resolved or cand_resolved.startswith(root_resolved + os.sep)):
    raise PathTraversalError(f"resolved path escapes target dir: {candidate}")
