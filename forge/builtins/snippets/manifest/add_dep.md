---
type: action
inputs: [authoring_vault_dir, dep_name, dep_version]
description: Add or update a dependency in the authoring vault's forge.toml.
---

# English

Read the forge.toml from authoring_vault_dir. Add or update the
dependency entry for dep_name at dep_version. Write the manifest back.
Return the updated manifest. If no manifest exists, create one with
defaults: name derived from the vault directory's basename
(sanitized to match the manifest name format), version "0.0.0",
description "Authoring vault."

# Python

```python
def compute(context):
  import os
  import re
  from pathlib import Path
  from forge.core.manifest import (
    Manifest,
    read_manifest,
    write_manifest,
    add_or_update_dep,
  )

  vault_dir = Path(context["authoring_vault_dir"])
  manifest_path = vault_dir / "forge.toml"

  if manifest_path.is_file():
    manifest = read_manifest(vault_dir)
  else:
    manifest = Manifest(
      name=_default_name(str(vault_dir)),
      version="0.0.0",
      description="Authoring vault.",
    )

  updated = add_or_update_dep(manifest, context["dep_name"], context["dep_version"])
  write_manifest(vault_dir, updated)
  return updated


def _default_name(vault_dir):
  import os, re
  base = os.path.basename(os.path.normpath(vault_dir)).lower()
  base = re.sub(r"[^a-z0-9-]", "-", base)
  base = re.sub(r"-+", "-", base).strip("-")
  if not re.match(r"^[a-z][a-z0-9-]{2,63}$", base):
    return "authoring-vault"
  return base
```
