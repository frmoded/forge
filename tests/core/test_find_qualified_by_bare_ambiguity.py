"""v0.2.84 Item B — tests for find_qualified_by_bare_all.

Powers the freeze modal disambiguation: when [[chorus]] matches
multiple qualified snippets across the registry, the plugin needs
ALL candidates so the user can pick. Pre-v0.2.84 only the first
match was returned, silently shadowing the others.

The existing `find_qualified_by_bare` (Optional[dict]) is kept as
a thin first-match wrapper for backward compat with v0.2.78
callers (the qualifier path uses it for the single-match case;
freeze switches to _all).
"""
import os
import tempfile
import pytest

from forge.core.snippet_registry import (
  SnippetRegistry, AUTHORING_VAULT, _collision_warning_set,
)


def _write_manifest(dirpath, name, version="0.1.0"):
  os.makedirs(dirpath, exist_ok=True)
  with open(os.path.join(dirpath, "forge.toml"), "w") as f:
    f.write(
      f'name = "{name}"\nversion = "{version}"\n'
      f'description = "test library"\n')


def _write_snippet(filepath, body="# English\n\nDo nothing.\n"):
  os.makedirs(os.path.dirname(filepath), exist_ok=True)
  with open(filepath, "w") as f:
    f.write("---\ntype: action\ninputs: []\n---\n\n" + body)


@pytest.fixture(autouse=True)
def reset_collision_warning_set():
  _collision_warning_set.clear()
  yield
  _collision_warning_set.clear()


def test_find_all_single_match_returns_one_element_list():
  """Unambiguous bare basename — _all returns [snippet]."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_manifest(vault, "vault", "1.0")
    _write_manifest(os.path.join(vault, "forge-music"), "forge-music", "0.3")
    _write_snippet(os.path.join(vault, "forge-music", "blues", "chorus.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    matches = reg.find_qualified_by_bare_all("chorus")
    assert len(matches) == 1
    assert matches[0]["snippet_id"] == "forge-music/blues/chorus"


def test_find_all_no_match_returns_empty_list():
  """Bare name with no match anywhere → []."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_manifest(vault, "vault", "1.0")

    reg = SnippetRegistry()
    reg.scan(vault)
    assert reg.find_qualified_by_bare_all("nonexistent") == []


def test_find_all_multiple_library_matches_returns_all():
  """`chorus` exists in both forge-music/blues/ AND forge-music/jazz/
  → _all returns BOTH in resolution order (alphabetical sort of
  subdirs since neither is a declared dep)."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_manifest(vault, "vault", "1.0")
    _write_manifest(os.path.join(vault, "forge-music"), "forge-music", "0.3")
    _write_snippet(os.path.join(vault, "forge-music", "blues", "chorus.md"))
    _write_snippet(os.path.join(vault, "forge-music", "jazz", "chorus.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    matches = reg.find_qualified_by_bare_all("chorus")
    assert len(matches) == 2
    ids = {m["snippet_id"] for m in matches}
    assert ids == {"forge-music/blues/chorus", "forge-music/jazz/chorus"}


def test_find_all_cross_vault_matches_returned():
  """`song` in BOTH forge-music AND forge-moda → both returned."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_manifest(vault, "vault", "1.0")
    _write_manifest(os.path.join(vault, "forge-music"), "forge-music", "0.3")
    _write_manifest(os.path.join(vault, "forge-moda"), "forge-moda", "0.4")
    _write_snippet(os.path.join(vault, "forge-music", "blues", "song.md"))
    _write_snippet(os.path.join(vault, "forge-moda", "scenes", "song.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    matches = reg.find_qualified_by_bare_all("song")
    assert len(matches) == 2
    ids = {m["snippet_id"] for m in matches}
    assert "forge-music/blues/song" in ids
    assert "forge-moda/scenes/song" in ids


def test_find_qualified_by_bare_first_wrapper_unchanged_for_single_match():
  """Backward-compat: existing `find_qualified_by_bare` (Optional[dict])
  callers (the qualifier path at pyodide-host.ts:_forge_qualify_snippet_id)
  see no behavior change for single-match cases."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    _write_manifest(vault, "vault", "1.0")
    _write_manifest(os.path.join(vault, "forge-music"), "forge-music", "0.3")
    _write_snippet(os.path.join(vault, "forge-music", "blues", "chorus.md"))

    reg = SnippetRegistry()
    reg.scan(vault)
    one = reg.find_qualified_by_bare("chorus")
    assert one is not None
    assert one["snippet_id"] == "forge-music/blues/chorus"
