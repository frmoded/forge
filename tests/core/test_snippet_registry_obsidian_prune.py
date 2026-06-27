"""v0.2.208 — SnippetRegistry must prune .obsidian/ from authoring walks.

Per the v0.2.193 rename-drain pebble: bundled-vault SOURCE COPIES under
`.obsidian/plugins/forge-client-obsidian/assets/vaults/<lib>/<note>.md`
were being walked by SnippetRegistry.scan as authoring snippets. The
copies have the same basenames as the freshly-extracted library vaults
at the user's vault top level — first-match-wins meant a stale bundled
copy could shadow a freshly edited source note.

Structural fix (v0.2.208): added `.obsidian` to `_RESERVED_DIRS` so
os.walk doesn't descend into it at any level. Belt-and-suspenders also
added `.git` and `.stfolder` (no .md inside, but the prune skips
useless I/O at sync-time).

These tests build a minimal vault with the exact directory shape that
triggered the bug and confirm:
  1. Bundled copies under .obsidian/ are NOT in the registry.
  2. Source-repo notes ARE in the registry.
  3. .git/ and .stfolder/ entries (defensive) don't leak either.
"""
from __future__ import annotations

import os
import tempfile
from textwrap import dedent

import pytest

from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT


def _write(path: str, content: str) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    f.write(content)


def _action_note(name: str, marker: str) -> str:
  return dedent(f"""\
    ---
    type: action
    ---
    # Description
    {marker}
    # Recipe
    Return.
    """).lstrip()


@pytest.fixture
def vault_with_bundled_shadow(tmp_path):
  """A vault that triggers the v0.2.193 pebble:

  bluh/
    note_in_authoring.md           # real authoring note
    .obsidian/plugins/forge-client-obsidian/assets/vaults/
      forge-music/percussion/solitary.md   # bundled-vault SHADOW copy
                                          # (basename collides with source)
    forge-music/                  # actual library vault at top level
      forge.toml
      percussion/solitary.md      # SOURCE-OF-TRUTH copy
  """
  vault = str(tmp_path / "bluh")
  os.makedirs(vault, exist_ok=True)

  # Real authoring note (sanity check that real notes still register).
  _write(
    os.path.join(vault, "note_in_authoring.md"),
    _action_note("note_in_authoring", "AUTHORING"),
  )

  # Top-level library: should register under "forge-music" namespace.
  _write(os.path.join(vault, "forge-music", "forge.toml"),
         'name = "forge-music"\nversion = "0.5.3"\ndescription = "music vault"\n')
  _write(
    os.path.join(vault, "forge-music", "percussion", "solitary.md"),
    _action_note("solitary", "SOURCE"),
  )

  # Bundled SHADOW under .obsidian/. Pre-fix this leaked into the
  # AUTHORING vault namespace with bare_id `solitary`.
  bundled = os.path.join(
    vault, ".obsidian", "plugins", "forge-client-obsidian",
    "assets", "vaults", "forge-music", "percussion",
  )
  _write(
    os.path.join(bundled, "solitary.md"),
    _action_note("solitary", "BUNDLED-SHADOW"),
  )

  # Belt-and-suspenders defensive prunes (.git, .stfolder). A .git/note.md
  # is contrived but the prune saves walk I/O.
  _write(os.path.join(vault, ".git", "note.md"),
         _action_note("gitnote", "FROM-DOT-GIT"))
  _write(os.path.join(vault, ".stfolder", "note.md"),
         _action_note("stfoldernote", "FROM-DOT-STFOLDER"))

  return vault


def test_obsidian_subtree_not_scanned_into_authoring(vault_with_bundled_shadow):
  """Pre-v0.2.208: bundled-vault copies under .obsidian/plugins/.../
  assets/vaults/forge-music/percussion/solitary.md leaked into the
  AUTHORING vault namespace as bare_id `solitary`, shadowing user
  edits to forge-music/percussion/solitary.md (the source).
  """
  reg = SnippetRegistry()
  reg.scan(vault_with_bundled_shadow)
  authoring = reg.get_in_vault(AUTHORING_VAULT, "solitary")
  # `solitary` MUST NOT be present in authoring — it belongs to the
  # forge-music library namespace, not authoring.
  assert authoring is None, (
    f"solitary leaked into authoring namespace from a bundled copy: "
    f"{authoring.get('path') if authoring else None!r}"
  )


def test_top_level_library_vault_still_registers(vault_with_bundled_shadow):
  """Sanity: the source-of-truth forge-music library at the user's
  vault top level still registers + is reachable as forge-music/
  percussion/solitary."""
  reg = SnippetRegistry()
  reg.scan(vault_with_bundled_shadow)
  src = reg.get_in_vault("forge-music", "percussion/solitary")
  assert src is not None
  assert src["body"].strip().endswith("Return.")
  # Spot-check: this is the SOURCE copy, not the bundled-shadow.
  assert "SOURCE" in src["body"]
  assert "BUNDLED-SHADOW" not in src["body"]


def test_authoring_notes_still_register(vault_with_bundled_shadow):
  """Sanity: notes at the user's vault top level (not under a library
  subdir) still register in the authoring namespace as before."""
  reg = SnippetRegistry()
  reg.scan(vault_with_bundled_shadow)
  auth = reg.get_in_vault(AUTHORING_VAULT, "note_in_authoring")
  assert auth is not None
  assert "AUTHORING" in auth["body"]


def test_dot_git_and_dot_stfolder_pruned(vault_with_bundled_shadow):
  """Belt-and-suspenders: .git/ and .stfolder/ also don't leak.
  These are contrived setups (no real .md in .git/), but the prune
  saves walk I/O on every scan + protects against weird user states.
  """
  reg = SnippetRegistry()
  reg.scan(vault_with_bundled_shadow)
  assert reg.get_in_vault(AUTHORING_VAULT, "gitnote") is None
  assert reg.get_in_vault(AUTHORING_VAULT, "stfoldernote") is None


def test_cohort_pure_bundled_user_unbroken(tmp_path):
  """Cohort user who only has bundled vaults (no source-repo): the
  vault top level has the freshly-extracted library directories (not
  the .obsidian/-stored sources). Registry must still resolve their
  chips.

  Pre-Phase 1, the bundled copies under .obsidian/ were a backup for
  re-extraction on version bump; the actively-used content is always
  at the top level. This test confirms we haven't broken that
  workflow.
  """
  vault = str(tmp_path / "cohort_bluh")
  os.makedirs(vault, exist_ok=True)
  _write(os.path.join(vault, "forge-music", "forge.toml"),
         'name = "forge-music"\nversion = "0.5.3"\ndescription = "music vault"\n')
  _write(
    os.path.join(vault, "forge-music", "percussion", "solitary.md"),
    _action_note("solitary", "EXTRACTED"),
  )
  reg = SnippetRegistry()
  reg.scan(vault)
  out = reg.get_in_vault("forge-music", "percussion/solitary")
  assert out is not None
  assert "EXTRACTED" in out["body"]
