"""v0.2.82 Item A — tests for AUTHORING-vault basename collision warn.

AUTHORING vault entries are keyed by basename (per
`_index_authoring_file:396`). If a user has `notes/chorus.md` AND
`songs/chorus.md`, both index as `_vaults["authoring"]["chorus"]`
during scan — last-write-wins by directory traversal order. The
second insert silently shadows the first; user sees one Forge-click
behavior for `[[chorus]]` and no signal that a second `chorus.md`
exists.

v0.2.82 fix: detect the collision at insertion time. Log a clear
warning identifying BOTH paths + which one is kept (first-match wins
per A4 walking contract). Module-scoped dedup set so a re-scan in
the same Pyodide-instance lifetime only warns once per (vault,
basename) pair.

Library vault entries use sub-path keys (per `_scan_library_vault`,
e.g. `_vaults["forge-music"]["blues/song"]`) so the same shape of
collision doesn't apply there — same-basename in different subdirs
produces distinct sub-path keys.
"""
import os
import tempfile
import pytest

from forge.core.snippet_registry import (
  SnippetRegistry, AUTHORING_VAULT, _collision_warning_set,
)


def _write_snippet(filepath, body="# English\n\nDo nothing.\n"):
  os.makedirs(os.path.dirname(filepath), exist_ok=True)
  with open(filepath, "w") as f:
    f.write(
      "---\ntype: action\ninputs: []\n---\n\n" + body)


@pytest.fixture(autouse=True)
def reset_collision_warning_set():
  """The dedup set is module-scoped; clear between tests so each
  test sees a fresh warning state."""
  _collision_warning_set.clear()
  yield
  _collision_warning_set.clear()


def test_authoring_vault_single_basename_no_collision_no_warning(capfd):
  """No two files with same basename → no warning emitted."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_snippet(os.path.join(vault, "notes", "chorus.md"))
    _write_snippet(os.path.join(vault, "songs", "verse.md"))

    reg = SnippetRegistry()
    reg.scan(vault)

    out, _ = capfd.readouterr()
    assert "collision" not in out.lower(), (
      f"Unexpected collision warning when basenames are unique: {out!r}")
    # Both files must be indexed (no shadowing).
    assert reg.get_in_vault(AUTHORING_VAULT, "chorus") is not None
    assert reg.get_in_vault(AUTHORING_VAULT, "verse") is not None


def test_authoring_vault_collision_fires_warning(capfd):
  """Same basename in two subdirs → warning emitted, first-match
  wins (subsequent insert is skipped)."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_snippet(
      os.path.join(vault, "notes", "chorus.md"),
      body="# English\n\nFirst chorus.\n")
    _write_snippet(
      os.path.join(vault, "songs", "chorus.md"),
      body="# English\n\nSecond chorus.\n")

    reg = SnippetRegistry()
    reg.scan(vault)

    out, _ = capfd.readouterr()
    assert "collision" in out.lower(), (
      f"Expected collision warning but stdout was: {out!r}")
    # Both paths must appear in the warning.
    assert "notes/chorus.md" in out or "notes\\chorus.md" in out
    assert "songs/chorus.md" in out or "songs\\chorus.md" in out

    # Only one entry survives; the resolved snippet has the
    # first-indexed body (deterministic by os.walk order — alphabetical).
    survivor = reg.get_in_vault(AUTHORING_VAULT, "chorus")
    assert survivor is not None
    # `notes/` comes before `songs/` alphabetically per os.walk.
    assert "First chorus" in survivor["body"], (
      f"First-match should win; got body: {survivor['body'][:80]!r}")


def test_authoring_vault_collision_warning_deduped_in_same_session(capfd):
  """Re-scanning the same vault in the same session must NOT
  re-warn for the same (vault, basename) collision."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_snippet(os.path.join(vault, "a", "chorus.md"))
    _write_snippet(os.path.join(vault, "b", "chorus.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    out1, _ = capfd.readouterr()
    assert "collision" in out1.lower()

    # Second scan: dedup should suppress the warning.
    reg2 = SnippetRegistry()
    reg2.scan(vault)
    out2, _ = capfd.readouterr()
    assert "collision" not in out2.lower(), (
      f"Second scan re-warned (dedup failed): {out2!r}")


def test_library_vault_same_basename_in_different_subdirs_no_warning(capfd):
  """Library vaults use sub-path keys (blues/chorus, hymns/chorus).
  These are distinct keys; no collision; no warning."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    # Authoring vault manifest.
    with open(os.path.join(vault, "forge.toml"), "w") as f:
      f.write('name = "vault"\nversion = "1.0"\ndescription = "test"\n')
    # Library forge-music with two same-basename snippets in subdirs.
    lib_path = os.path.join(vault, "forge-music")
    os.makedirs(lib_path)
    with open(os.path.join(lib_path, "forge.toml"), "w") as f:
      f.write(
        'name = "forge-music"\nversion = "0.3"\ndescription = "test"\n')
    _write_snippet(os.path.join(lib_path, "blues", "chorus.md"))
    _write_snippet(os.path.join(lib_path, "hymns", "chorus.md"))

    reg = SnippetRegistry()
    reg.scan(vault)

    out, _ = capfd.readouterr()
    assert "collision" not in out.lower(), (
      f"Library sub-path entries should not collide: {out!r}")
    # Both library entries indexed under distinct sub-path keys.
    assert reg.get_in_vault("forge-music", "blues/chorus") is not None
    assert reg.get_in_vault("forge-music", "hymns/chorus") is not None


def test_authoring_vault_multiple_collisions_each_warns_once(capfd):
  """Two distinct collision pairs (chorus + verse) → two warnings,
  each for its own pair. Re-scan: zero warnings (both deduped)."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_snippet(os.path.join(vault, "a", "chorus.md"))
    _write_snippet(os.path.join(vault, "b", "chorus.md"))
    _write_snippet(os.path.join(vault, "a", "verse.md"))
    _write_snippet(os.path.join(vault, "b", "verse.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    out, _ = capfd.readouterr()
    # Count occurrences of the word "collision" — should be two
    # distinct warnings.
    assert out.lower().count("collision") == 2, (
      f"Expected 2 collision warnings (one per pair); got: {out!r}")
    assert "chorus" in out
    assert "verse" in out
