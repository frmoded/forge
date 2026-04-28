---
type: action
inputs: [vault_name, version]
description: Install a vault from the Forge registry into the user's Obsidian vault.
---

# English

Install a vault from the Forge registry. Steps:
1. Look up the vault in the registry to get its tarball URL and SHA-256.
2. Download the tarball and verify its integrity.
3. Extract it into the user's Obsidian vault as a folder named after the vault.
4. Record the installed dependency in the user's forge.toml.
5. Refresh the snippet registry so the new vault is immediately usable.
After install, try `[[<vault_name>/...]]` to invoke any of its snippets.

# Python

```python
def run(context):
  from pathlib import Path

  if context.vault_path is None:
    raise RuntimeError("install requires an active session vault_path")

  vault_name = context["vault_name"]
  version = context.get("version")

  entry = context.execute(
    "forge/registry/lookup",
    vault_name=vault_name,
    version=version,
  )

  tarball_path = context.execute(
    "forge/registry/fetch",
    tarball_url=entry["tarball"],
    expected_sha256=entry["sha256"],
  )

  target_dir = str(Path(context.vault_path) / vault_name)
  context.execute(
    "forge/vault/extract",
    tarball_path=tarball_path,
    target_dir=target_dir,
  )

  context.execute(
    "forge/manifest/add_dep",
    authoring_vault_dir=context.vault_path,
    dep_name=vault_name,
    dep_version=entry["version"],
  )

  context.execute("forge/registry/refresh")

  return f"Installed {vault_name}@{entry['version']}"
```
