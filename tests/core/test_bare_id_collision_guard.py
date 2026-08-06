"""[2026-08-05-2200-cw-plugin-bare-id-collision-fix] — bare-id lookups
over a collided basename must raise, not silently run the wrong twin.

Mechanism (a) from drain 2100: AUTHORING vault entries are keyed by
basename alone, so two files like `authoring/postproc_hello.md` and
`ccqa-scratch/postproc_hello.md` fight over one registry key. Since
v0.2.82 the loser is skipped at index time with only a console.warn —
by lookup time the ambiguity is invisible and `get_bare` returns the
scan-order winner. A Run on the shadowed note silently executes its
twin.

Fix under test: `scan`/`refresh_file` record same-vault basename
collisions; `get_bare` raises AmbiguousSnippetResolutionError naming
both vault-relative paths with a rename instruction. The guard
self-heals when a twin's file no longer exists on disk, and a fresh
scan resets the record. Cross-VAULT shadowing (authoring note over a
library note, A4 walking order) is intentional and must NOT raise —
covered here against forge-music / forge-moda / forge-tutorial
library names per L11.
"""
import os
import pytest

from forge.core.snippet_registry import (
  SnippetRegistry, AUTHORING_VAULT, _collision_warning_set,
)
from forge.core.graph_resolver import GraphResolver
from forge.core.exceptions import AmbiguousSnippetResolutionError


def _write_note(filepath, body="# Description\n\nA note.\n\n# Recipe\nReturn 1.\n"):
  os.makedirs(os.path.dirname(filepath), exist_ok=True)
  with open(filepath, "w") as f:
    f.write("---\ntype: action\ninputs: []\n---\n\n" + body)


def _lib_toml(lib_path, name):
  os.makedirs(lib_path, exist_ok=True)
  with open(os.path.join(lib_path, "forge.toml"), "w") as f:
    f.write(f'name = "{name}"\nversion = "0.1"\ndescription = "test"\n')


@pytest.fixture(autouse=True)
def reset_collision_warning_set():
  _collision_warning_set.clear()
  yield
  _collision_warning_set.clear()


def test_bare_id_collision_raises_ambiguous(tmp_path):
  """The drain-2200 reproducer: same-basename twins in two subdirs.
  Pre-fix: get_bare returned the scan-order winner (authoring/ twin)
  with no error. Post-fix: legible AmbiguousSnippetResolutionError."""
  _write_note(
    str(tmp_path / "authoring" / "postproc_hello.md"),
    body="# Description\n\nEmpty twin.\n\n# Recipe\n")
  _write_note(
    str(tmp_path / "ccqa-scratch" / "postproc_hello.md"),
    body="# Description\n\nReal fixture.\n\n# Recipe\nReturn 'hello'.\n")

  reg = SnippetRegistry()
  reg.scan(str(tmp_path))

  with pytest.raises(AmbiguousSnippetResolutionError) as exc_info:
    reg.get_bare("postproc_hello")
  msg = str(exc_info.value)
  assert "authoring/postproc_hello.md" in msg
  assert "ccqa-scratch/postproc_hello.md" in msg
  assert "ename" in msg  # "Rename"/"rename" instruction present


def test_resolver_bare_lookup_propagates_ambiguity(tmp_path):
  """GraphResolver.resolve on a bare id (no caller context — the
  runSnippet shape) must surface the same error, not first-match."""
  _write_note(str(tmp_path / "a" / "chorus.md"))
  _write_note(str(tmp_path / "b" / "chorus.md"))

  reg = SnippetRegistry()
  reg.scan(str(tmp_path))
  resolver = GraphResolver(reg)

  with pytest.raises(AmbiguousSnippetResolutionError):
    resolver.resolve("chorus")


def test_single_subdir_note_still_resolves(tmp_path):
  """No twin → no behavior change: bare lookup finds the subdir note."""
  _write_note(str(tmp_path / "ccqa-scratch" / "postproc_hello.md"))

  reg = SnippetRegistry()
  reg.scan(str(tmp_path))

  hit = reg.get_bare("postproc_hello")
  assert hit is not None
  assert hit["snippet_id"] == f"{AUTHORING_VAULT}/postproc_hello"


def test_cross_vault_shadow_does_not_raise(tmp_path):
  """A4 walking order: an authoring note shadowing same-basename
  notes in library vaults is intentional — no ambiguity error.
  L11 coverage: forge-music + forge-moda + forge-tutorial."""
  with open(tmp_path / "forge.toml", "w") as f:
    f.write('name = "vault"\nversion = "1.0"\ndescription = "test"\n')
  _write_note(str(tmp_path / "chorus.md"),
              body="# Description\n\nAuthoring wins.\n\n# Recipe\nReturn 1.\n")
  for lib in ("forge-music", "forge-moda", "forge-tutorial"):
    _lib_toml(str(tmp_path / lib), lib)
    _write_note(str(tmp_path / lib / "chorus.md"))

  reg = SnippetRegistry()
  reg.scan(str(tmp_path))

  hit = reg.get_bare("chorus")
  assert hit is not None
  assert hit["vault"] == AUTHORING_VAULT
  assert "Authoring wins" in hit["body"]


def test_collision_self_heals_when_twin_deleted(tmp_path):
  """Once one twin's file is gone from disk, the ambiguity no longer
  exists NOW — the guard verifies liveness and lets the survivor
  resolve (covers delete-without-rescan in native/headless flows)."""
  _write_note(str(tmp_path / "a" / "chorus.md"),
              body="# Description\n\nKept.\n\n# Recipe\nReturn 1.\n")
  _write_note(str(tmp_path / "b" / "chorus.md"))

  reg = SnippetRegistry()
  reg.scan(str(tmp_path))
  with pytest.raises(AmbiguousSnippetResolutionError):
    reg.get_bare("chorus")

  os.remove(str(tmp_path / "b" / "chorus.md"))
  hit = reg.get_bare("chorus")
  assert hit is not None
  assert "Kept" in hit["body"]


def test_refresh_file_created_twin_after_scan_raises(tmp_path):
  """The live-session sequence: vault scanned clean, then a twin is
  created and synced via refresh_file — the collision must be
  recorded on the incremental path too."""
  _write_note(str(tmp_path / "authoring" / "postproc_hello.md"))
  reg = SnippetRegistry()
  reg.scan(str(tmp_path))
  assert reg.get_bare("postproc_hello") is not None

  twin = str(tmp_path / "ccqa-scratch" / "postproc_hello.md")
  _write_note(twin)
  reg.refresh_file(twin)

  with pytest.raises(AmbiguousSnippetResolutionError):
    reg.get_bare("postproc_hello")


def test_rescan_after_rename_clears_collision(tmp_path):
  """Idempotent no-op contract: a fresh scan derives collision state
  from disk. Twins present → still raises; twin renamed → resolves."""
  _write_note(str(tmp_path / "a" / "chorus.md"))
  _write_note(str(tmp_path / "b" / "chorus.md"))

  reg = SnippetRegistry()
  reg.scan(str(tmp_path))
  with pytest.raises(AmbiguousSnippetResolutionError):
    reg.get_bare("chorus")

  reg.scan(str(tmp_path))
  with pytest.raises(AmbiguousSnippetResolutionError):
    reg.get_bare("chorus")

  os.rename(str(tmp_path / "b" / "chorus.md"),
            str(tmp_path / "b" / "chorus_two.md"))
  reg.scan(str(tmp_path))
  assert reg.get_bare("chorus") is not None
  assert reg.get_bare("chorus_two") is not None
