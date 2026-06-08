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
# v0.2.78 — `<library>.bak.<old-version>/` directories created by the
# v0.2.38 auto-re-extract mechanism are user-facing backups of stale
# library content. They retain an intact forge.toml (literal directory
# copy), so _detect_library_vaults would otherwise index them as live
# libraries — either colliding on the library name with the fresh
# extract (last-write-wins by sort order, stale bodies leak in) or
# producing snippet_ids like `forge-tutorial.bak.0.1.0/<path>` that
# the plugin sees when the user clicks a backup file (resolver raises
# SnippetResolutionError because the vault name isn't registered).
# Pattern is exactly the rename in welcome.ts:renameWithBackup —
# `<name>.bak.<version>` with optional `.<n>` collision suffix.
import re
_BAK_DIR_PATTERN = re.compile(r"\.bak\.")

# v0.2.82 Item A — dedup set for AUTHORING-vault basename-collision
# warnings. Module-scoped so multiple SnippetRegistry instances share
# the same dedup state across a single Pyodide-instance lifetime
# (matches the v0.2.81 _forge_facet_form_warning_set pattern: browser
# reload resets, re-warn). Entries are (vault_name, bare_id) tuples.
_collision_warning_set = set()


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
        # v0.2.78 — also prune `<base>.bak.<version>/` backup dirs from
        # the authoring traversal. Otherwise the .md files inside the
        # backup would be indexed as AUTHORING snippets (still wrong:
        # the user would see stale duplicates of every library snippet
        # in chip palettes / qualified lookups).
        dirs[:] = [d for d in dirs if not _BAK_DIR_PATTERN.search(d)]
      # Skip Forge-managed state dirs at every level (snapshot files in
      # .forge/edges/ would otherwise shadow real snippets).
      dirs[:] = [d for d in dirs if d not in _RESERVED_DIRS]
      # v0.2.82 Item A — sort dirs + files so traversal order is
      # deterministic. AUTHORING-vault basename-collisions resolve via
      # first-match-wins (per the v0.2.82 collision-detect fix in
      # _index_authoring_file); deterministic order is what makes that
      # contract stable across rescans. os.walk's default order is
      # filesystem-dependent.
      dirs.sort()
      for fname in sorted(files):
        if fname.endswith(".md"):
          err = self._index_authoring_file(
            os.path.join(root, fname), vault_name, source, vault_path,
          )
          if err:
            self.errors.append(err)
      del files  # release the unsorted ref (we iterated `sorted(files)`)

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

  def refresh_file(self, filepath: str, vault_name: Optional[str] = None, source: Optional[str] = None) -> Optional[str]:
    """v0.2.17: re-index a single file from disk and update the cached
    entry. Used by the forge-client-obsidian plugin to keep the
    MEMFS-mounted registry in sync with disk edits (writeGeneratedCode,
    direct editor saves) without paying the full vault-scan cost.

    Returns an error string if indexing failed (same shape as scan()'s
    self.errors entries), None on success.

    v0.2.74 fix (Hypothesis A pin): when `vault_name` is None, detect
    the owning vault by finding the longest `vault_path` prefix among
    all indexed entries. This routes refreshes for library snippets at
    `<vault>/<lib>/foo.md` to `_vaults[<lib>][foo]` (or sub-path-keyed
    `_vaults[<lib>][sub/foo]`) instead of leaking them into
    `AUTHORING['foo']` (the v0.2.73 bug — the library entry stayed
    stale-since-install while the AUTHORING entry collected the
    refresh nobody read).

    Explicit `vault_name` (legacy callers) still forces that vault,
    preserving v0.2.17 behavior. The plugin's `_forge_sync_user_file`
    helper at pyodide-host.ts calls this with no `vault_name` argument
    and benefits from the auto-detection.

    Fallback: if no indexed vault claims the filepath, falls back to
    AUTHORING_VAULT keyed by basename — the right default for "write
    into an empty vault" / pre-scan file creation cases.
    """
    if vault_name is not None:
      # Legacy path: caller specified the vault explicitly. Honor it.
      vault_path = None
      if vault_name in self._vaults:
        for entry in self._vaults[vault_name].values():
          vault_path = entry.get("vault_path")
          if vault_path:
            break
      if not vault_path:
        vault_path = os.path.dirname(filepath)
      self._vaults.setdefault(vault_name, {})
      return self._index_authoring_file(
        filepath, vault_name, source or "authoring", vault_path)

    # Auto-detect owning vault: longest vault_path prefix wins.
    abs_filepath = os.path.abspath(filepath)
    best_vault_name = None
    best_vault_path = None
    best_source = None
    for vname, snippets in self._vaults.items():
      for entry in snippets.values():
        vp = entry.get("vault_path")
        if not vp:
          continue
        vp_abs = os.path.abspath(vp)
        # Boundary-safe prefix match: `/vault/foo` must not match
        # `/vault/foo-bar/x.md`. Compare against vp + os.sep.
        prefix = vp_abs.rstrip(os.sep) + os.sep
        if abs_filepath.startswith(prefix) or abs_filepath == vp_abs:
          if best_vault_path is None or len(vp_abs) > len(best_vault_path):
            best_vault_name = vname
            best_vault_path = vp_abs
            best_source = entry.get("source", "authoring")

    if best_vault_name is None:
      # No vault claims this path — fall back to AUTHORING under the
      # file's parent directory. Matches the pre-v0.2.74 behavior for
      # the "write into an empty vault" / pre-scan case.
      vault_path_fallback = os.path.dirname(filepath)
      self._vaults.setdefault(AUTHORING_VAULT, {})
      return self._index_authoring_file(
        filepath, AUTHORING_VAULT, source or "authoring",
        vault_path_fallback)

    if best_source == "library":
      return self._index_library_file(
        filepath, best_vault_name, best_vault_path)
    return self._index_authoring_file(
      filepath, best_vault_name, source or best_source or "authoring",
      best_vault_path)

  def _index_library_file(self, filepath: str, vault_name: str, vault_path: str) -> Optional[str]:
    """v0.2.74: single-file refresh path for library snippets. Mirrors
    the bare_id convention from `_scan_library_vault` (relpath-keyed,
    OS-separators normalized to forward slashes)."""
    try:
      with open(filepath, encoding="utf-8") as f:
        content = f.read()
      meta, body = parse_frontmatter(content)
      rel = os.path.relpath(filepath, vault_path)
      bare_id = os.path.splitext(rel)[0].replace(os.sep, "/")
      if meta.get("type") in _RECOGNIZED_TYPES:
        self._vaults.setdefault(vault_name, {})
        self._vaults[vault_name][bare_id] = {
          "meta": meta,
          "body": body,
          "path": filepath,
          "vault": vault_name,
          "vault_path": vault_path,
          "source": "library",
          "snippet_id": f"{vault_name}/{bare_id}",
        }
      return None
    except Exception as e:
      return f"{filepath}: {e}"

  def get_bare(self, bare_id: str) -> Optional[dict]:
    """Walk the resolution order, return the first match. Direct-key
    lookup only — preserves the A4 walking semantics other callers
    depend on (caller-vault precedence, declared dependency order).

    For qualifier paths that need to find a snippet by basename
    regardless of resolution-order membership (e.g. freeze on a
    library wikilink whose parent library isn't a declared
    dependency of the authoring vault), see `find_qualified_by_bare`."""
    for vault_name in self._order:
      hit = self._vaults.get(vault_name, {}).get(bare_id)
      if hit is not None:
        return hit
    return None

  def find_qualified_by_bare(self, bare_id: str) -> Optional[dict]:
    """v0.2.78 — locate a snippet by its bare basename anywhere in
    the registry, regardless of resolution-order membership. Used by
    `_forge_qualify_snippet_id` to resolve freeze-modal wikilink
    targets like `[[chorus]]` to their qualified id
    `forge-music/blues/chorus` so the freeze path finds the snapshot
    the capture path wrote at the qualified key.

    Lookup order:
      Pass 1: direct key match in resolution-order vaults (matches
              authoring-vault top-level + library top-level entries).
      Pass 2: direct key match in NON-resolution-order vaults (covers
              libraries the authoring vault hasn't declared as deps —
              freeze on a library wikilink still needs to qualify).
      Pass 3: basename scan across sub-path keys, resolution-order
              vaults first, then non-resolution-order vaults. Library
              entries are stored under `<subdir>/<name>` keys; the
              basename scan picks up wikilink-bare references.
    First match wins. Returns the same shape `get_bare` does."""
    order_set = set(self._order)
    # Pass 1: direct-key lookup, resolution-order vaults.
    for vault_name in self._order:
      hit = self._vaults.get(vault_name, {}).get(bare_id)
      if hit is not None:
        return hit
    # Pass 2: direct-key lookup, other vaults.
    for vault_name, snippets in self._vaults.items():
      if vault_name in order_set:
        continue
      hit = snippets.get(bare_id)
      if hit is not None:
        return hit
    # Pass 3: basename scan across sub-path keys.
    for vault_name in self._order:
      for key, snip in self._vaults.get(vault_name, {}).items():
        if "/" in key and key.rsplit("/", 1)[-1] == bare_id:
          return snip
    for vault_name, snippets in self._vaults.items():
      if vault_name in order_set:
        continue
      for key, snip in snippets.items():
        if "/" in key and key.rsplit("/", 1)[-1] == bare_id:
          return snip
    return None

  def find_qualified_by_bare_all(self, bare_id: str) -> list:
    """v0.2.84 — like `find_qualified_by_bare` but returns ALL matches
    in resolution order (resolution-order vaults first, then non-
    resolution-order vaults; within each, direct-key matches first
    then sub-path basename matches). Used by the freeze handler to
    disambiguate when a bare wikilink like `[[chorus]]` matches more
    than one snippet (e.g. `forge-music/blues/chorus` AND
    `forge-music/jazz/chorus`).

    Deduplicated by qualified `snippet_id` — a snippet that matches
    via both Pass 1 (direct key) AND Pass 3 (basename scan against
    a sub-path key) is returned exactly once. The first pass wins
    the position.

    Returns empty list when no match. Single match → 1-element list
    (caller does its own len-check)."""
    order_set = set(self._order)
    seen_ids = set()
    out = []

    def _try_append(snip):
      sid = snip.get("snippet_id")
      if sid and sid not in seen_ids:
        seen_ids.add(sid)
        out.append(snip)

    # Pass 1: direct-key, resolution-order vaults.
    for vault_name in self._order:
      hit = self._vaults.get(vault_name, {}).get(bare_id)
      if hit is not None:
        _try_append(hit)
    # Pass 2: direct-key, non-resolution-order vaults.
    for vault_name, snippets in self._vaults.items():
      if vault_name in order_set:
        continue
      hit = snippets.get(bare_id)
      if hit is not None:
        _try_append(hit)
    # Pass 3: basename scan across sub-path keys, resolution-order first.
    for vault_name in self._order:
      for key, snip in self._vaults.get(vault_name, {}).items():
        if "/" in key and key.rsplit("/", 1)[-1] == bare_id:
          _try_append(snip)
    for vault_name, snippets in self._vaults.items():
      if vault_name in order_set:
        continue
      for key, snip in snippets.items():
        if "/" in key and key.rsplit("/", 1)[-1] == bare_id:
          _try_append(snip)
    return out

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
      # v0.2.78 — skip `<base>.bak.<anything>` directories. These are
      # backups left behind by welcome.ts:renameWithBackup after
      # v0.2.38's auto-re-extract; treating them as libraries either
      # collides on the library name (stale bodies leak via
      # last-write-wins in scan order) or produces unroutable
      # snippet_ids when the user clicks a backup file.
      if _BAK_DIR_PATTERN.search(entry):
        continue
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
        # v0.2.82 Item A — basename collision detection. AUTHORING
        # entries are keyed by basename alone (per the historical
        # contract — see _scan_library_vault for the sub-path-keyed
        # library counterpart). Same-basename files in different
        # subdirs silently shadowed each other pre-v0.2.82. Detect at
        # insertion time, log + skip subsequent insert so first-match
        # wins per the A4 walking contract. Dedup'd per (vault, bare_id)
        # via module-scoped _collision_warning_set so re-scans in the
        # same session warn once.
        existing = self._vaults[vault_name].get(bare_id)
        # Only treat as collision when the existing entry came from a
        # DIFFERENT path. Same-path re-index (refresh_file rewriting
        # the same file after disk edit) is the legitimate update
        # path — refresh_file's whole point is overwriting cached
        # state with fresh disk contents. Use os.path.abspath for
        # robust comparison against vault-relative variations.
        if existing is not None and (
          os.path.abspath(existing.get("path", "")) != os.path.abspath(filepath)
        ):
          dedup_key = (vault_name, bare_id)
          if dedup_key not in _collision_warning_set:
            _collision_warning_set.add(dedup_key)
            msg = (
              f"Forge: snippet collision in vault '{vault_name}' on "
              f"basename '{bare_id}'. Indexed: {existing['path']!r}. "
              f"Shadowed: {filepath!r}. First-match wins. Rename one "
              f"to disambiguate."
            )
            try:
              import js
              js.console.warn(msg)
            except Exception:
              # Defensive — Pyodide js module unavailable (test envs).
              print(msg)
          # Do NOT overwrite — preserve first-match-wins semantics.
          return None
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
