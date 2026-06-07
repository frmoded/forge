"""v0.2.74 — investigation test for Hypothesis A (SnippetRegistry
refresh_file writes to wrong vault when the file belongs to a library
subdir, not the authoring vault root).

Reproduces the v0.2.73 driver bug: cache miss every Forge-click on
slot_demo.md despite consistent on-disk english_hash. Root cause:
the plugin calls _forge_sync_user_file on the snippet path, which
calls SnippetRegistry.refresh_file. refresh_file defaults
vault_name to AUTHORING_VAULT and uses os.path.basename for bare_id.
For a file at `<vault>/forge-moda/slot_demo.md` (library subdir),
this writes to `_vaults[AUTHORING][slot_demo]` instead of
`_vaults['forge-moda'][slot_demo]`. The library entry stays STALE.

When the plugin compute looks up `forge-moda/slot_demo`, A4 goes
DIRECT to `_vaults['forge-moda'][slot_demo]` (qualified IDs bypass
the authoring walk) → returns the STALE entry → english_hash is
the OLD value or # Python is missing → cache miss every click.
"""
import os
import shutil
import tempfile
import pytest

from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT


def _make_vault_with_library(tmpdir):
  """Build a vault structure mimicking ~/forge-vaults/bluh/:
    bluh/
      forge.toml          ← user's authoring vault manifest
      forge-moda/         ← library subdir (extracted from bundle)
        forge.toml        ← library manifest
        slot_demo.md      ← the snippet under test
  """
  vault = os.path.join(tmpdir, "bluh")
  os.makedirs(vault)
  os.makedirs(os.path.join(vault, "forge-moda"))

  with open(os.path.join(vault, "forge.toml"), "w") as f:
    f.write('name = "bluh"\nversion = "1.0"\ndescription = "test"\n')
  with open(os.path.join(vault, "forge-moda", "forge.toml"), "w") as f:
    f.write(
      'name = "forge-moda"\nversion = "0.4.19"\ndescription = "test lib"\n')

  # Initial slot_demo state (post-cache-write under v0.2.72/v0.2.73:
  # has english_hash matching # English + # Python heading).
  with open(os.path.join(vault, "forge-moda", "slot_demo.md"), "w") as f:
    f.write(
      "---\n"
      "type: action\n"
      "inputs: []\n"
      "facet_form: canonical\n"
      "english_hash: f44f75cfaa0c23cd390f587cddd56718f6639de5be62e918ccdafe0cc4b635db\n"
      "---\n"
      "\n# English\n\n"
      "Set greeting to {{a friendly hello message in the style of a children's storybook}}.\n"
      "Do [[print]](greeting).\n"
      "\n# Python\n\n"
      "```python\n"
      "def compute(context):\n"
      '    greeting = "Once upon a time, in a land far, far away..."\n'
      "    print(greeting)\n"
      "```\n"
    )
  return vault


def test_hypothesis_a_refresh_file_writes_to_wrong_vault_for_library_snippet():
  """Reproduces the v0.2.74 bug. After refresh_file, the library
  entry should reflect the updated disk state. v0.2.73 it doesn't
  because refresh_file writes to AUTHORING_VAULT keyed by basename
  instead of <library>/<basename>."""
  with tempfile.TemporaryDirectory() as tmpdir:
    vault = _make_vault_with_library(tmpdir)
    reg = SnippetRegistry()
    reg.scan(vault)

    slot_demo_path = os.path.join(vault, "forge-moda", "slot_demo.md")

    # Initial state: library entry has english_hash f44f75cf.
    initial = reg.get("forge-moda/slot_demo")
    assert initial is not None, (
      "After scan(), `forge-moda/slot_demo` must resolve to the "
      "library entry. If this fails, the scan path itself is wrong.")
    initial_hash = initial["meta"].get("english_hash")
    assert initial_hash == (
      "f44f75cfaa0c23cd390f587cddd56718f6639de5be62e918ccdafe0cc4b635db")

    # Simulate: plugin edits slot_demo (changes english_hash on disk).
    NEW_HASH = "0" * 64
    with open(slot_demo_path, "r") as f:
      body = f.read()
    body_updated = body.replace(initial_hash, NEW_HASH)
    with open(slot_demo_path, "w") as f:
      f.write(body_updated)

    # Plugin calls refresh_file on the updated file (mimicking
    # _forge_sync_user_file's post-write registry refresh).
    err = reg.refresh_file(slot_demo_path)
    assert err is None, f"refresh_file unexpectedly errored: {err}"

    # The library entry must now reflect the new disk state.
    post = reg.get("forge-moda/slot_demo")
    assert post is not None, (
      "After refresh_file, `forge-moda/slot_demo` must STILL resolve "
      "to the library entry (the path the engine sees on compute).")
    post_hash = post["meta"].get("english_hash")
    assert post_hash == NEW_HASH, (
      f"Hypothesis A CONFIRMED: refresh_file did NOT update the "
      f"library entry's english_hash.\n"
      f"  Expected: {NEW_HASH}\n"
      f"  Got     : {post_hash}\n"
      f"  Library entry stayed STALE — the bug shape."
    )
