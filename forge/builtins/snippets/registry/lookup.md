---
type: action
inputs: [vault_name, version]
description: Look up a vault in the Forge registry.
---

# English

Fetch the registry index, find vault_name, resolve to version (or
latest if omitted), and return the tarball URL, SHA-256, and resolved
version.

# Python

```python
def compute(context):
  from forge.config import get_config
  from forge.installer.registry_client import fetch_index, lookup
  cfg = get_config()
  index = fetch_index(cfg.registry_url)
  return lookup(index, context["vault_name"], context.get("version"))
```
