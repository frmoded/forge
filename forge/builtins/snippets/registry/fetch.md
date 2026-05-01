---
type: action
inputs: [tarball_url, expected_sha256]
description: Download a vault tarball and verify its SHA-256.
---

# English

Download the tarball at tarball_url. Verify its SHA-256 matches
expected_sha256. Cache the verified tarball by SHA so reinstalls of
the same version are instant. Return the local path.

# Python

```python
def compute(context):
  from pathlib import Path
  from forge.config import get_config
  from forge.installer.http import download_to_file
  from forge.installer.hashing import verify_sha256

  cfg = get_config()
  cache_root = cfg.cache_dir / "tarballs"
  cache_root.mkdir(parents=True, exist_ok=True)

  expected = context["expected_sha256"]
  cached = cache_root / f"{expected}.tar.gz"
  if cached.is_file():
    verify_sha256(cached, expected)  # paranoid re-check; corruption clears the cache
    return str(cached)

  download_to_file(context["tarball_url"], cached)
  verify_sha256(cached, expected)
  return str(cached)
```
