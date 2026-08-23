"""Drain 2026-08-23-1400 — the create_water_particles failure.

CCQA's registry dumps (test-reports/2026-08-22-2118-registry-probe-dump.md)
showed the failing vault carrying `.forge/edges/`-derived entries of
`type: "snapshot"` whose path-shaped ids contain `create_water_particles`
as their last segment. The prompt attributed the ingestion to the
plugin's MEMFS mount. It reproduces without any plugin involvement:

  SnippetRegistry.scan()
    -> authoring traversal DOES prune _RESERVED_DIRS (drain 1600 §5
       proved this, and test_authoring_traversal_still_excludes_reserved
       below keeps proving it)
    -> _scan_library_vault does NOT: it walks `for root, _, files in
       os.walk(lib_path)`, discarding the dirs list, so it cannot prune
       and carries no reserved-dir filter at all.

Library vaults are sub-path keyed, so the entry lands as
`.forge/edges/authoring/setup/authoring/create_water_particles`.
`_build_snippet_shims` keys shims by BASENAME, so it installs a
`create_water_particles` shim that shadows the engine chip; dispatch
then asks `get_bare('create_water_particles')`, which has no such exact
key, and the user gets SnippetResolutionError.

Two indexes, one shadowing decision — the hazard CC's 2026-08-22-2010
message named. This suite pins both layers:

  (a) neither engine walk ingests reserved dirs, and refresh_file
      refuses them too (it is the plugin's per-file sync path and had
      no exclusion either),
  (b) the shim set is resolvable BY CONSTRUCTION: a shim is installed
      only when dispatch could actually resolve its name.

(b) is tested with (a) bypassed, so the belt is shown to hold alone.
"""

import os

import pytest

from forge.core.executor import _build_snippet_shims, _DOMAIN_GLOBALS
from forge.core.snippet_registry import SnippetRegistry


CHIP_NAME = "create_water_particles"
EDGE_SUBPATH = os.path.join(
  ".forge", "edges", "authoring", "setup", "authoring")


def _library_vault(tmp_path, *, with_edge_snapshot=True):
  """A vault holding one library vault, shaped like a real install."""
  vault = tmp_path / "vault"
  lib = vault / "forge-moda"
  (lib / EDGE_SUBPATH).mkdir(parents=True)
  (lib / "forge.toml").write_text(
    'name = "forge-moda"\nversion = "0.5.4"\n'
    'description = "d"\ndomains = ["moda"]\n')
  (lib / "go.md").write_text("---\ntype: action\n---\n\n# Recipe\nprint(1)\n")
  if with_edge_snapshot:
    (lib / EDGE_SUBPATH / f"{CHIP_NAME}.md").write_text(
      "---\ntype: snapshot\n---\n\nbody\n")
  return vault


class _FakeContext:
  def compute(self, *args, **kwargs):  # pragma: no cover - never called
    raise AssertionError("shim dispatch not expected in these tests")


def _ids(registry):
  return {
    vault: sorted(entries.keys())
    for vault, entries in registry._vaults.items()
  }


# --------------------------------------------------------------- (a)

def test_library_scan_excludes_forge_state_dirs(tmp_path):
  """The reproduction. RED before this drain."""
  registry = SnippetRegistry()
  registry.scan(str(_library_vault(tmp_path)), "authoring", "authoring")

  lib_ids = _ids(registry)["forge-moda"]
  assert lib_ids == ["go"], (
    f"library scan ingested Forge-managed state: {lib_ids}")


def test_authoring_traversal_still_excludes_reserved(tmp_path):
  """Non-vacuity for the pruning claim: the authoring walk was already
  correct, and must stay correct."""
  vault = tmp_path / "plain"
  (vault / ".forge" / "edges").mkdir(parents=True)
  (vault / "note.md").write_text("---\ntype: action\n---\n\nx\n")
  (vault / ".forge" / "edges" / f"{CHIP_NAME}.md").write_text(
    "---\ntype: snapshot\n---\n\nbody\n")

  registry = SnippetRegistry()
  registry.scan(str(vault), "authoring", "authoring")
  assert _ids(registry)["authoring"] == ["note"]


def test_refresh_file_refuses_reserved_paths(tmp_path):
  """The plugin's per-file sync path (syncUserVaultFile -> refresh_file)
  had no exclusion either: it ingested a file scan() had just correctly
  skipped. Same rule, one definition."""
  vault = tmp_path / "plain"
  (vault / ".forge" / "edges").mkdir(parents=True)
  (vault / "note.md").write_text("---\ntype: action\n---\n\nx\n")
  snapshot = vault / ".forge" / "edges" / f"{CHIP_NAME}.md"
  snapshot.write_text("---\ntype: snapshot\n---\n\nbody\n")

  registry = SnippetRegistry()
  registry.scan(str(vault), "authoring", "authoring")
  registry.refresh_file(str(snapshot))

  assert _ids(registry)["authoring"] == ["note"], (
    "refresh_file ingested a reserved-dir file")


def test_a_real_note_still_refreshes(tmp_path):
  """Non-vacuity for the refusal: refresh_file must still do its job."""
  vault = tmp_path / "plain"
  vault.mkdir()
  (vault / "note.md").write_text("---\ntype: action\n---\n\nx\n")
  registry = SnippetRegistry()
  registry.scan(str(vault), "authoring", "authoring")

  added = vault / "later.md"
  added.write_text("---\ntype: action\n---\n\ny\n")
  registry.refresh_file(str(added))
  assert _ids(registry)["authoring"] == ["later", "note"]


# --------------------------------------------------------------- (b)

def _registry_with_unresolvable_entry():
  """(a) deliberately bypassed: the phantom is injected straight into
  the index, which is what proves the belt holds on its own."""
  registry = SnippetRegistry()
  registry._vaults["forge-moda"] = {
    f"{EDGE_SUBPATH.replace(os.sep, '/')}/{CHIP_NAME}": {
      "meta": {"type": "snapshot"},
      "body": "body",
      "path": "/x.md",
      "vault_path": "/x",
      "source": "authoring",
      "snippet_id": f"forge-moda/{EDGE_SUBPATH}/{CHIP_NAME}",
    },
    "go": {
      "meta": {"type": "action"},
      "body": "print(1)",
      "path": "/go.md",
      "vault_path": "/",
      "source": "authoring",
      "snippet_id": "forge-moda/go",
    },
  }
  registry.set_resolution_order(["forge-moda"])
  return registry


def test_shims_are_resolvable_by_construction():
  """A shim whose name dispatch cannot resolve must not be installed —
  it would shadow an engine chip and then fail to dispatch."""
  registry = _registry_with_unresolvable_entry()
  shims = _build_snippet_shims(_FakeContext(), registry)

  assert CHIP_NAME not in shims, (
    "installed a shim for an entry get_bare cannot resolve")
  assert "go" in shims, "dropped a shim dispatch CAN resolve"


def test_the_unresolvable_entry_really_is_unresolvable():
  """Non-vacuity: the fixture's phantom must genuinely miss get_bare,
  or the assertion above proves nothing."""
  registry = _registry_with_unresolvable_entry()
  assert registry.get_bare(CHIP_NAME) is None
  assert registry.get_bare("go") is not None


def test_no_shim_shadows_an_engine_chip_it_cannot_serve():
  """The end-to-end invariant, stated over the real chip set: every
  installed shim that collides with an engine chip name must be one
  dispatch can actually resolve."""
  registry = _registry_with_unresolvable_entry()
  shims = _build_snippet_shims(_FakeContext(), registry)
  chips = {name for bundle in _DOMAIN_GLOBALS.values() for name in bundle}

  unserviceable = sorted(
    name for name in set(shims) & chips if registry.get_bare(name) is None)
  assert unserviceable == [], (
    f"these shims shadow an engine chip but cannot dispatch: {unserviceable}")


def test_chip_name_is_a_real_engine_chip():
  """Non-vacuity for the test above: if create_water_particles stopped
  being a chip, the collision it guards could not occur and the guard
  would be green for the wrong reason."""
  chips = {name for bundle in _DOMAIN_GLOBALS.values() for name in bundle}
  assert CHIP_NAME in chips
