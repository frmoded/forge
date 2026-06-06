import os
from typing import Optional
import yaml

AUTHORING_VAULT = "authoring"
BUILTIN_VAULT = "forge"
_MANIFEST_FILENAME = "forge.toml"
_RECOGNIZED_TYPES = ("action", "data", "snapshot")
# Forge-managed state directories that must not be walked as snippet sources.
# .forge/edges/ holds auto-captured snapshots; if those leaked into the
# registry they'd shadow the real snippets they were captured from.
_RESERVED_DIRS = {".forge"}


class SnippetRegistry:
  def __init__(self):
    # vault_name -> bare_id -> snippet
    self._vaults: dict = {}
    self._order: list = [AUTHORING_VAULT, BUILTIN_VAULT]
    self.errors: list = []

  def scan(self, vault_path, vault_name: str = AUTHORING_VAULT, source: str = "authoring"):
    """Scan a filesystem vault.

    Top-level subdirectories that contain a forge.toml are treated as library
    vaults and indexed under their own namespace (per ADR 0001/0002). All other
    .md files are indexed under vault_name.
    """
    self.errors = []
    self._vaults[vault_name] = {}
    vault_path = os.fspath(vault_path)

    library_dirs = self._detect_library_vaults(vault_path)
    library_dir_names = {os.path.basename(p) for p in library_dirs}

    for root, dirs, files in os.walk(vault_path):
      if root == vault_path:
        # prune library vault subdirs from the authoring traversal
        dirs[:] = [d for d in dirs if d not in library_dir_names]
      # Skip Forge-managed state dirs at every level (snapshot files in
      # .forge/edges/ would otherwise shadow real snippets).
      dirs[:] = [d for d in dirs if d not in _RESERVED_DIRS]
      for fname in files:
        if fname.endswith(".md"):
          err = self._index_authoring_file(
            os.path.join(root, fname), vault_name, source, vault_path,
          )
          if err:
            self.errors.append(err)

    for lib_path in library_dirs:
      self._scan_library_vault(lib_path)

    self._auto_set_resolution_order(vault_path)

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

  def refresh_file(self, filepath: str, vault_name: str = AUTHORING_VAULT, source: str = "authoring") -> Optional[str]:
    """v0.2.17: re-index a single file from disk and update the cached
    entry. Used by the forge-client-obsidian plugin to keep the
    MEMFS-mounted registry in sync with disk edits (writeGeneratedCode,
    direct editor saves) without paying the full vault-scan cost.

    Returns an error string if indexing failed (same shape as scan()'s
    self.errors entries), None on success.

    vault_path is inferred from an existing entry in `vault_name` —
    works for the V1 single-user-vault model where the plugin only
    ever calls this against the authoring vault. If no entries exist
    yet (registry never scanned), falls back to the file's parent
    directory, which is the right default for "write into an empty
    vault" cases."""
    vault_path = None
    if vault_name in self._vaults:
      for entry in self._vaults[vault_name].values():
        vault_path = entry.get("vault_path")
        if vault_path:
          break
    if not vault_path:
      vault_path = os.path.dirname(filepath)
    # Ensure the per-vault dict exists; _index_authoring_file writes
    # into self._vaults[vault_name] directly.
    self._vaults.setdefault(vault_name, {})
    return self._index_authoring_file(filepath, vault_name, source, vault_path)

  def get_bare(self, bare_id: str) -> Optional[dict]:
    """Walk the resolution order, return the first match."""
    for vault_name in self._order:
      hit = self._vaults.get(vault_name, {}).get(bare_id)
      if hit is not None:
        return hit
    return None

  def find_in_sibling_subdirs(
      self, vault_name: str, caller_dir: str, bare_id: str,
  ) -> list:
    """Probe 2 helper for A4.1's V2a v8 extension.

    Enumerate all keys in `vault_name` matching `<sibling>/<bare_id>`
    where `<sibling>` is a top-level subdir of the vault AND
    `<sibling> != caller_dir`. Returns the matching subdir-relative
    keys (e.g. `percussion_lab/solitary`) sorted alphabetically for
    deterministic error messages on ambiguity.

    Nested subdirs (e.g. `foo/bar/<bare_id>`) are NOT included — the
    extension is single-level-sibling by design. Caller's own subdir
    is excluded because Probe 1 already covered it.

    Returns empty list when no siblings match; caller (graph_resolver
    Probe 2) handles len(0) vs len(1) vs len(2+) dispatch."""
    snippets = self._vaults.get(vault_name, {})
    matches = []
    for bare in snippets.keys():
      if "/" not in bare:
        continue  # vault-root snippet, not a sibling-subdir candidate
      head, _, tail = bare.partition("/")
      if tail != bare_id:
        continue  # different bare_id under this subdir
      if head == caller_dir:
        continue  # caller's own dir — Probe 1 territory
      matches.append(bare)
    matches.sort()
    return matches

  def get(self, snippet_id: str) -> Optional[dict]:
    """Smart dispatch: qualified ('vault/bare') goes direct; bare walks order."""
    if "/" in snippet_id:
      vault_name, bare = snippet_id.split("/", 1)
      return self.get_in_vault(vault_name, bare)
    return self.get_bare(snippet_id)

  def loaded_vaults(self) -> list:
    return list(self._vaults.keys())

  def list_snippets(self) -> dict:
    """Return {vault_name: [{id, type, inputs}, ...]} sorted by id.

    `type` is taken from frontmatter, defaults to 'action'. `inputs` is the
    declared input list (defaults to []). The plugin falls back to this list
    when running an action whose local .md has no frontmatter (e.g. an empty
    stub file in the user's vault that overlays a builtin)."""
    return {
      vault: [
        {
          "id": bare_id,
          "type": snippets[bare_id]["meta"].get("type", "action"),
          "inputs": list(snippets[bare_id]["meta"].get("inputs") or []),
        }
        for bare_id in sorted(snippets.keys())
      ]
      for vault, snippets in self._vaults.items()
    }

  def resolution_order(self) -> list:
    return list(self._order)

  # --- internals ---

  def _detect_library_vaults(self, vault_path: str) -> list:
    if not os.path.isdir(vault_path):
      return []
    out = []
    for entry in sorted(os.listdir(vault_path)):
      sub = os.path.join(vault_path, entry)
      if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, _MANIFEST_FILENAME)):
        out.append(sub)
    return out

  def _scan_library_vault(self, lib_path: str) -> Optional[str]:
    try:
      from forge.core.manifest import read_manifest
      m = read_manifest(lib_path)
      name = m.name
    except Exception as e:
      self.errors.append(f"{lib_path}: failed to read library manifest: {e}")
      return None

    self._vaults[name] = {}
    for root, _, files in os.walk(lib_path):
      for fname in files:
        if not fname.endswith(".md"):
          continue
        filepath = os.path.join(root, fname)
        try:
          with open(filepath, encoding="utf-8") as f:
            content = f.read()
          meta, body = parse_frontmatter(content)
          rel = os.path.relpath(filepath, lib_path)
          bare_id = os.path.splitext(rel)[0].replace(os.sep, "/")
          if meta.get("type") in _RECOGNIZED_TYPES:
            self._vaults[name][bare_id] = {
              "meta": meta,
              "body": body,
              "path": filepath,
              "vault": name,
              "vault_path": lib_path,
              "source": "library",
              "snippet_id": f"{name}/{bare_id}",
            }
        except Exception as e:
          self.errors.append(f"{filepath}: {e}")
    return name

  def _auto_set_resolution_order(self, vault_path: str) -> None:
    manifest_path = os.path.join(vault_path, _MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
      return
    try:
      from forge.core.manifest import read_manifest
      m = read_manifest(vault_path)
    except Exception as e:
      self.errors.append(f"{manifest_path}: {e}")
      return
    lib_order = [d.name for d in m.dependencies]
    self.set_resolution_order([AUTHORING_VAULT, *lib_order])

  def _index_authoring_file(self, filepath: str, vault_name: str, source: str, vault_path: str) -> Optional[str]:
    try:
      with open(filepath, encoding="utf-8") as f:
        content = f.read()
      meta, body = parse_frontmatter(content)
      bare_id = os.path.splitext(os.path.basename(filepath))[0]
      if meta.get("type") in _RECOGNIZED_TYPES:
        self._vaults[vault_name][bare_id] = {
          "meta": meta,
          "body": body,
          "path": filepath,
          "vault": vault_name,
          "vault_path": vault_path,
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
