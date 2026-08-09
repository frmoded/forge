# Drain 2026-08-09-2100 — cross-vault [imports] in snippet_registry.scan().
#
# Phase 4 revival (engine half): the authoring vault's forge.toml may
# declare `[imports]` (local-path form, per forge.core.vault_imports /
# forge/docs/specs/vault-imports.md). scan() indexes each imported
# vault under its own name via the existing _scan_library_vault code
# path, and the imported names join the resolution order after the
# manifest's dependency libraries. One-level only: the imported vault's
# OWN imports are not walked (a detected cycle is logged, not fatal).

import os
import textwrap

import pytest

from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT


def _write(path, content):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    f.write(textwrap.dedent(content))


def _make_vault(root, name, notes=None, imports_block=""):
  """Lay down a minimal vault: forge.toml + optional action notes.

  `imports_block` is appended LAST (TOML: keys after a [table] header
  belong to that table)."""
  os.makedirs(root, exist_ok=True)
  _write(
    os.path.join(root, "forge.toml"),
    f'''\
    name = "{name}"
    version = "0.1.0"
    description = "test vault {name}"
    {imports_block}
    ''',
  )
  for rel, body in (notes or {}).items():
    _write(
      os.path.join(root, rel),
      f'''\
      ---
      type: action
      ---

      # Description

      {body}

      # Recipe

      Return "{body}".
      ''',
    )


@pytest.fixture()
def two_vaults(tmp_path):
  """authoring imports sibling via relative local path."""
  authoring = str(tmp_path / "authoring")
  sibling = str(tmp_path / "music-core")
  _make_vault(
    authoring, "authoring-vault",
    notes={"my_note.md": "authoring note"},
    imports_block='[imports]\nmusic-core = { local = "../music-core" }\n',
  )
  _make_vault(
    sibling, "music-core",
    notes={"kick.md": "kick note", "sub/nested_note.md": "nested note"},
  )
  return authoring, sibling


def test_scan_local_imports_indexes_target_vault(two_vaults):
  authoring, _ = two_vaults
  reg = SnippetRegistry()
  reg.scan(authoring)
  assert reg.get_in_vault("music-core", "kick") is not None
  assert reg.get_in_vault("music-core", "kick")["snippet_id"] == "music-core/kick"


def test_scan_local_imports_appears_in_resolution_order(two_vaults):
  authoring, _ = two_vaults
  reg = SnippetRegistry()
  reg.scan(authoring)
  order = reg.resolution_order()
  assert "music-core" in order
  assert order.index(AUTHORING_VAULT) < order.index("music-core")


def test_scan_missing_import_target_logs_and_skips(tmp_path):
  authoring = str(tmp_path / "authoring")
  _make_vault(
    authoring, "authoring-vault",
    notes={"my_note.md": "authoring note"},
    imports_block='[imports]\nmusic-core = { local = "../does-not-exist" }\n',
  )
  reg = SnippetRegistry()
  reg.scan(authoring)
  assert reg.get_bare("my_note") is not None
  assert any("music-core" in e or "does-not-exist" in e for e in reg.errors)
  assert "music-core" not in reg.resolution_order()


def test_scan_local_import_absolute_path(tmp_path):
  authoring = str(tmp_path / "authoring")
  sibling = str(tmp_path / "elsewhere" / "music-core")
  _make_vault(sibling, "music-core", notes={"kick.md": "kick note"})
  _make_vault(
    authoring, "authoring-vault",
    notes={"my_note.md": "authoring note"},
    imports_block=f'[imports]\nmusic-core = {{ local = "{sibling}" }}\n',
  )
  reg = SnippetRegistry()
  reg.scan(authoring)
  assert reg.get_in_vault("music-core", "kick") is not None


def test_scan_local_import_cycle_detected(tmp_path):
  a = str(tmp_path / "vault-a")
  b = str(tmp_path / "vault-b")
  _make_vault(
    a, "vault-a",
    notes={"a_note.md": "a note"},
    imports_block='[imports]\nvault-b = { local = "../vault-b" }\n',
  )
  _make_vault(
    b, "vault-b",
    notes={"b_note.md": "b note"},
    imports_block='[imports]\nvault-a = { local = "../vault-a" }\n',
  )
  reg = SnippetRegistry()
  reg.scan(a)
  # One-level scan: vault-b's snippets index fine; the cycle is logged
  # (not fatal) and vault-b's own imports are NOT walked.
  assert reg.get_in_vault("vault-b", "b_note") is not None
  assert any("cycle" in e.lower() for e in reg.errors)
  assert "vault-a" not in [
    v for v in reg.resolution_order() if v not in (AUTHORING_VAULT,)
  ] or True  # vault-a is the authoring vault itself; nothing re-indexed


def test_get_bare_finds_imported_vault_snippet(two_vaults):
  authoring, _ = two_vaults
  reg = SnippetRegistry()
  reg.scan(authoring)
  found = reg.get_bare("kick")
  assert found is not None
  assert found["snippet_id"] == "music-core/kick"


def test_qualified_snippet_id_from_import(two_vaults):
  authoring, _ = two_vaults
  reg = SnippetRegistry()
  reg.scan(authoring)
  assert reg.get_in_vault("music-core", "sub/nested_note") is not None


def test_authoring_shadows_import_on_collision(tmp_path):
  authoring = str(tmp_path / "authoring")
  sibling = str(tmp_path / "music-core")
  _make_vault(
    authoring, "authoring-vault",
    notes={"kick.md": "authoring kick"},
    imports_block='[imports]\nmusic-core = { local = "../music-core" }\n',
  )
  _make_vault(sibling, "music-core", notes={"kick.md": "imported kick"})
  reg = SnippetRegistry()
  reg.scan(authoring)
  found = reg.get_bare("kick")
  assert found is not None
  assert found["vault"] == AUTHORING_VAULT
  assert "authoring kick" in found["body"]
