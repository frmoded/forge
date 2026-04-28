import hashlib
from pathlib import Path
from forge.installer.exceptions import HashMismatchError

_CHUNK = 64 * 1024


def sha256_of_file(path: Path) -> str:
  h = hashlib.sha256()
  with open(path, "rb") as f:
    while True:
      chunk = f.read(_CHUNK)
      if not chunk:
        break
      h.update(chunk)
  return h.hexdigest()


def verify_sha256(path: Path, expected_hex: str) -> None:
  actual = sha256_of_file(path)
  if actual.lower() != expected_hex.lower():
    raise HashMismatchError(actual=actual, expected=expected_hex)
