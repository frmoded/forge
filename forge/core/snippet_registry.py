import os
from typing import Optional
import yaml

AUTHORING_VAULT = "authoring"
BUILTIN_VAULT = "forge"


class SnippetRegistry:
  def __init__(self):
    # vault_name -> bare_id -> snippet
    self._vaults: dict = {}
    self._order: list = [AUTHORING_VAULT, BUILTIN_VAULT]
    self.errors: list = []

  def scan(self, vault_path, vault_name: str = AUTHORING_VAULT, source: str = "authoring"):
    """Scan a filesystem vault, indexing every .md file with type=action|data."""
    self.errors = []
    self._vaults[vault_name] = {}
    for root, _, files in os.walk(vault_path):
      for fname in files:
        if fname.endswith(".md"):
          err = self._index(os.path.join(root, fname), vault_name, source)
          if err:
            self.errors.append(err)

  def register_builtin_vault(self, snippets: list) -> None:
    """Ingest pre-parsed builtin snippets (from forge.builtins.loader)."""
    self._vaults[BUILTIN_VAULT] = {}
    for snippet in snippets:
      qualified = snippet["snippet_id"]
      vault = snippet["vault"]
      if "/" not in qualified:
        raise ValueError(f"builtin snippet_id missing namespace: {qualified}")
      ns, bare = qualified.split("/", 1)
      if ns != vault or vault != BUILTIN_VAULT:
        raise ValueError(f"builtin snippet vault mismatch: vault={vault} ns={ns}")
      self._vaults[BUILTIN_VAULT][bare] = snippet

  def set_resolution_order(self, vault_names: list) -> None:
    """Set the search order for bare references. Builtin vault is always last."""
    order = [v for v in vault_names if v != BUILTIN_VAULT]
    order.append(BUILTIN_VAULT)
    self._order = order

  def get_in_vault(self, vault_name: str, bare_id: str) -> Optional[dict]:
    return self._vaults.get(vault_name, {}).get(bare_id)

  def get_bare(self, bare_id: str) -> Optional[dict]:
    """Walk the resolution order, return the first match."""
    for vault_name in self._order:
      hit = self._vaults.get(vault_name, {}).get(bare_id)
      if hit is not None:
        return hit
    return None

  def get(self, snippet_id: str) -> Optional[dict]:
    """Smart dispatch: qualified ('vault/bare') goes direct; bare walks order."""
    if "/" in snippet_id:
      vault_name, bare = snippet_id.split("/", 1)
      return self.get_in_vault(vault_name, bare)
    return self.get_bare(snippet_id)

  def loaded_vaults(self) -> list:
    return list(self._vaults.keys())

  def resolution_order(self) -> list:
    return list(self._order)

  def _index(self, filepath: str, vault_name: str, source: str) -> Optional[str]:
    try:
      with open(filepath, encoding="utf-8") as f:
        content = f.read()
      meta, body = parse_frontmatter(content)
      bare_id = os.path.splitext(os.path.basename(filepath))[0]
      if meta.get("type") in ("action", "data"):
        self._vaults[vault_name][bare_id] = {
          "meta": meta,
          "body": body,
          "path": filepath,
          "vault": vault_name,
          "source": source,
          "snippet_id": f"{vault_name}/{bare_id}",
        }
      return None
    except Exception as e:
      return f"{filepath}: {e}"


def parse_frontmatter(content: str):
  """Public parser used by both filesystem scans and the builtin loader."""
  if not content.startswith("---"):
    return {}, content
  parts = content.split("---", 2)
  if len(parts) < 3:
    return {}, content
  meta = yaml.safe_load(parts[1]) or {}
  return meta, parts[2].strip()
