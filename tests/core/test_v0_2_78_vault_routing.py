"""v0.2.78 — vault routing hotfix investigation tests.

Two bugs surfaced by the 2026-06-07 mint-laptop smoke:

Bug A — SnippetRegistry scans `.bak.<version>/` directories as
libraries. v0.2.38's auto-re-extract creates `<library>.bak.<oldver>/`
backups beside the fresh library. Each contains an intact forge.toml
(it's a literal directory copy). `_detect_library_vaults` walks every
top-level subdir whose forge.toml exists — including the .bak. Two
problems:
  (i) The .bak's library name from manifest = `<lib>` (same as fresh)
      → collision: scan() overwrites _vaults['<lib>'] entries from the
      .bak's scan, depending on directory sort order.
  (ii) The plugin, computing snippet_id from a clicked file's path,
       produces `<lib>.bak.<ver>/<rel>` — which is not a registered
       vault name. Resolver raises SnippetResolutionError.

Bug B — `_forge_qualify_snippet_id` in pyodide-host.ts produces the
wrong qualified ID for library snippets stored under sub-path bare_ids.
The qualifier calls `registry.get_bare(bare_id)` which only matches
top-level keys per `_vaults[v][bare_id]`. Library entries are stored
under sub-path keys (e.g. `_vaults['forge-music']['blues/chorus']`,
NOT `_vaults['forge-music']['chorus']`). So `get_bare('chorus')` returns
None, the qualifier falls through unchanged, and `set_snapshot_state`
looks for a snapshot at `.forge/edges/chorus/song.md` which never
existed — capture wrote to `.forge/edges/forge-music/blues/song/forge-music/blues/chorus.md`.
FileNotFoundError on freeze.

Both share the architectural pattern v0.2.75 also hit in `refresh_file`:
"default to AUTHORING-or-bare for unknown vault membership."
"""
import os
import shutil
import tempfile
import pytest

from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT


def _write_manifest(dirpath, name, version="0.1.0"):
  os.makedirs(dirpath, exist_ok=True)
  with open(os.path.join(dirpath, "forge.toml"), "w") as f:
    f.write(
      f'name = "{name}"\nversion = "{version}"\n'
      f'description = "test library"\n')


def _write_snippet(filepath, type_="action", inputs=None, body="# English\n\nDo nothing.\n"):
  os.makedirs(os.path.dirname(filepath), exist_ok=True)
  inputs_str = "[]" if inputs is None else "[" + ", ".join(inputs) + "]"
  with open(filepath, "w") as f:
    f.write(
      f"---\ntype: {type_}\ninputs: {inputs_str}\n---\n\n{body}")


# ===========================================================
# Bug A: .bak.* libraries indexed alongside fresh ones
# ===========================================================

def test_bug_a_scan_excludes_bak_directories_from_library_discovery():
  """A vault containing forge-tutorial/ AND forge-tutorial.bak.0.1.0/
  must index ONLY the fresh forge-tutorial as a library.

  v0.2.77 indexes both because `_detect_library_vaults` walks every
  top-level subdir whose forge.toml exists — both contain one.

  The .bak entries are user-facing backups (per v0.2.38 design); they
  must NOT appear in the registry at all. The fix is at the discovery
  layer: exclude any top-level directory whose name matches
  `<base>.bak.<anything>` from library candidacy."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "smoke-vault")
    os.makedirs(vault)

    # Authoring vault forge.toml.
    _write_manifest(vault, "smoke-vault", "1.0")

    # Fresh forge-tutorial library at v0.1.1 (post-extract).
    _write_manifest(os.path.join(vault, "forge-tutorial"), "forge-tutorial", "0.1.1")
    _write_snippet(
      os.path.join(vault, "forge-tutorial", "01-hello", "hello_world.md"),
      body="# English\n\nFRESH BODY.\n",
    )

    # Stale backup at v0.1.0 (renamed by v0.2.38 mechanism).
    _write_manifest(os.path.join(vault, "forge-tutorial.bak.0.1.0"),
                    "forge-tutorial", "0.1.0")
    _write_snippet(
      os.path.join(vault, "forge-tutorial.bak.0.1.0", "01-hello", "hello_world.md"),
      body="# English\n\nSTALE BODY.\n",
    )

    reg = SnippetRegistry()
    reg.scan(vault)

    # The fresh tutorial must be present.
    fresh = reg.get("forge-tutorial/01-hello/hello_world")
    assert fresh is not None, (
      "Fresh forge-tutorial/01-hello/hello_world must be indexed.")
    assert "FRESH BODY" in fresh["body"], (
      f"Fresh entry should have FRESH BODY but has: {fresh['body'][:80]!r}.\n"
      f"This indicates the .bak overwrote it during scan (directory sort "
      f"order put .bak after fresh, last-write-wins per scan()'s loop).")

    # The .bak directory must NOT have produced any registry entries.
    # Three forms it could leak in as:
    #   1. A separate vault keyed by its directory name.
    #   2. Entries in `forge-tutorial` (the .bak's manifest declares
    #      the same name as the fresh).
    #   3. (Already asserted above) overwriting the fresh entry's body.
    bak_vault = reg.list_snippets().get("forge-tutorial.bak.0.1.0")
    assert bak_vault is None, (
      "`forge-tutorial.bak.0.1.0/` must NOT be indexed as a library. "
      f"Found {len(bak_vault) if bak_vault else 0} entries under that vault name.")


# ===========================================================
# Bug B: qualifier for bare IDs misses sub-path library entries
# ===========================================================

def test_bug_b_qualifier_resolves_library_subpath_basename():
  """`registry.get_bare('chorus')` against a vault where chorus lives
  at `forge-music/blues/chorus` must find it.

  Pre-v0.2.78 `get_bare` only searches `_vaults[v][bare_id]` per the
  resolution order — direct key lookup. Library entries are stored
  under sub-path keys (`_vaults['forge-music']['blues/chorus']`) so
  the bare basename `'chorus'` doesn't match the key `'blues/chorus'`.
  `get_bare` returns None; `_forge_qualify_snippet_id` falls through;
  freeze writes to `.forge/edges/chorus/song.md` which doesn't exist.

  The fix: extend `get_bare` (or add a sibling helper) to also scan
  by basename across sub-path keys. The capture path uses
  `snippet["snippet_id"]` which is always qualified by `<vault>/<bare>`,
  so the snapshot was written at the correct qualified path; freeze
  just needs to find that path."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "smoke-vault")
    os.makedirs(vault)

    _write_manifest(vault, "smoke-vault", "1.0")

    # Library forge-music with two sub-path snippets at blues/.
    _write_manifest(os.path.join(vault, "forge-music"), "forge-music", "0.3.10")
    _write_snippet(
      os.path.join(vault, "forge-music", "blues", "song.md"),
      body="# English\n\nDo [[chorus]]().\n",
    )
    _write_snippet(
      os.path.join(vault, "forge-music", "blues", "chorus.md"),
      body="# English\n\nReturn 'chorus body'.\n",
    )

    reg = SnippetRegistry()
    reg.scan(vault)

    # Sanity: the library snippets are indexed under sub-path keys.
    assert reg.get_in_vault("forge-music", "blues/chorus") is not None, (
      "Sanity: library should have blues/chorus key.")
    assert reg.get_in_vault("forge-music", "chorus") is None, (
      "Sanity: library is NOT keyed by basename — only sub-path.")

    # The bug: get_bare('chorus') misses the sub-path entry.
    found = reg.get_bare("chorus")
    assert found is not None, (
      "Bug B: `get_bare('chorus')` should find the library snippet at "
      "forge-music/blues/chorus by basename. Pre-v0.2.78 only matches "
      "top-level keys, so library sub-path entries are invisible to the "
      "bare lookup, breaking freeze qualifier for library wikilinks.")
    assert found["snippet_id"] == "forge-music/blues/chorus", (
      f"Resolved snippet must be the library entry; got {found['snippet_id']!r}.")


def test_bug_b_qualifier_basename_resolution_does_not_break_authoring_top_level():
  """Regression: authoring-vault top-level snippets keyed by basename
  must still resolve via get_bare. The new sub-path scan must not
  shadow the existing direct-key lookup."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "smoke-vault")
    os.makedirs(vault)
    _write_manifest(vault, "smoke-vault", "1.0")

    # An authoring-vault top-level snippet.
    _write_snippet(os.path.join(vault, "greet.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    found = reg.get_bare("greet")
    assert found is not None
    assert found["snippet_id"] == f"{AUTHORING_VAULT}/greet"


def test_bug_b_qualifier_basename_resolution_ambiguity_prefers_first():
  """When a basename matches multiple sub-path entries across vaults
  (e.g. forge-moda/setup AND forge-music/setup), the resolution order
  determines the winner — same as current bare-key semantics."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "smoke-vault")
    os.makedirs(vault)
    _write_manifest(vault, "smoke-vault", "1.0")

    _write_manifest(os.path.join(vault, "forge-music"), "forge-music", "0.3")
    _write_manifest(os.path.join(vault, "forge-moda"), "forge-moda", "0.4")
    _write_snippet(os.path.join(vault, "forge-music", "blues", "song.md"))
    _write_snippet(os.path.join(vault, "forge-moda", "scenes", "song.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    # Resolution order set by _auto_set_resolution_order from
    # smoke-vault's forge.toml deps — which we didn't declare, so
    # the order is [authoring, builtin]. Library vaults appear in
    # _vaults dict insertion order (which is filesystem sort:
    # forge-moda, forge-music alphabetically). The current
    # `get_bare` walks `_order` only — so it would only find the
    # authoring vault and builtin vault. With the fix that also
    # scans sub-path keys, we need to make sure the order is
    # respected — first vault wins.
    found = reg.get_bare("song")
    assert found is not None
    assert found["snippet_id"] in (
      "forge-music/blues/song", "forge-moda/scenes/song"), (
      f"Got {found['snippet_id']!r}; expected one of the library variants.")
