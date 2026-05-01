---
type: action
inputs: []
description: Trigger a rescan of installed vaults and notify connected clients.
---

# English

Re-scan the user's Obsidian vault to pick up newly-installed library
vaults. Notify any connected plugin clients that the snippet registry
has changed.

# Python

```python
def compute(context):
  if context.registry is None or context.vault_path is None:
    raise RuntimeError("registry/refresh requires registry and vault_path on context")
  context.registry.scan(context.vault_path)
  _notify_clients(context)
  return {
    "refreshed": True,
    "vault_path": context.vault_path,
    "vaults": context.registry.loaded_vaults(),
  }


def _notify_clients(context):
  # TODO Chunk E: broadcast registry-changed event to connected Obsidian clients.
  # Stubbed for Chunk C; tests assert this hook is reached.
  pass
```
