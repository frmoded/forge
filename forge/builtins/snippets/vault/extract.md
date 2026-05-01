---
type: action
inputs: [tarball_path, target_dir]
description: Extract a verified vault tarball into the user's Obsidian vault.
---

# English

Extract tarball_path into target_dir (creating it if needed),
stripping the top-level wrapper directory that GitHub adds. Verify
the extracted contents include a forge.toml at the root by reading
and parsing it. Return the parsed manifest along with the final
vault directory path.

# Python

```python
def compute(context):
  from pathlib import Path
  from forge.installer.tarball import extract_tarball
  from forge.core.manifest import read_manifest

  target = Path(context["target_dir"])
  extract_tarball(Path(context["tarball_path"]), target, strip_components=1)
  manifest = read_manifest(target)
  return {"vault_dir": str(target), "manifest": manifest}
```
