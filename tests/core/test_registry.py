import os
from pathlib import Path
from forge.core.snippet_registry import SnippetRegistry
from forge.core.graph_resolver import GraphResolver

VAULT = str(Path(__file__).parent.parent / "vault")


def test_scan_indexes_action_snippets():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  snippet = registry.get("hello_forge")
  assert snippet is not None
  assert snippet["meta"]["type"] == "action"


def test_scan_uses_filename_as_id():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  assert registry.get("hello_forge") is not None
  assert registry.get("greet") is not None
  assert registry.get("hello_world") is not None


def test_scan_populates_body():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  snippet = registry.get("hello_forge")
  assert snippet["body"]


def test_scan_produces_no_errors_on_clean_vault():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  assert registry.errors == []


def test_scan_skips_notes_without_type(tmp_path):
  (tmp_path / "untitled.md").write_text("---\n---\njust a note")
  registry = SnippetRegistry()
  registry.scan(str(tmp_path))
  assert registry.get("untitled") is None


def test_scan_reports_parse_errors(tmp_path):
  (tmp_path / "good.md").write_text("---\ntype: action\n---\n# Python\ncode")
  (tmp_path / "bad.md").write_text("---\ntype: action\n: broken: yaml:\n---\nbody")
  registry = SnippetRegistry()
  registry.scan(str(tmp_path))
  assert any("bad.md" in e for e in registry.errors)


def test_graph_resolver_finds_indexed_snippet():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  resolver = GraphResolver(registry)
  assert resolver.resolve("hello_forge") is not None


def test_graph_resolver_try_resolve_returns_none_for_missing():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  resolver = GraphResolver(registry)
  assert resolver.try_resolve("does_not_exist") is None


def test_graph_resolver_resolve_raises_for_missing():
  from forge.core.exceptions import SnippetResolutionError
  import pytest
  registry = SnippetRegistry()
  registry.scan(VAULT)
  resolver = GraphResolver(registry)
  with pytest.raises(SnippetResolutionError):
    resolver.resolve("does_not_exist")


# ---------------------------------------------------------------------------
# Two-vault refactor (constitution A5.1 / A5.2): library subdirectory
# convention + shadow resolution.
#
# A library vault installed at <user>/<library-name>/ is detected via its
# own forge.toml, indexed under the library namespace, and reachable via
# bare references through the parent vault's `dependencies` order. A
# same-bare-id snippet at the user-vault root SHADOWS the library copy
# (A4 order). These tests pin the engine guarantee that the two-vault
# pattern works without any new resolution rules.
# ---------------------------------------------------------------------------

def _make_two_vault_layout(tmp_path, shadow_present=True):
    user = tmp_path / "user_vault"
    lib = user / "forge-moda"
    lib.mkdir(parents=True)
    (user / "forge.toml").write_text(
        'name = "user-vault"\nversion = "0.1.0"\ndescription = "test"\n'
        'domains = []\n'
        'dependencies = [{ name = "forge-moda", version = "0.4.2" }]\n'
    )
    (lib / "forge.toml").write_text(
        'name = "forge-moda"\nversion = "0.4.2"\ndescription = "test"\n'
    )
    (lib / "leaf.md").write_text(
        '---\ntype: action\nrole: leaf\ninputs: []\n---\n\n'
        '# English\nReturn LIBRARY.\n\n'
        '# Python\n```python\ndef compute(context):\n    return "LIBRARY"\n```\n'
    )
    if shadow_present:
        (user / "leaf.md").write_text(
            '---\ntype: action\ninputs: []\n---\n\n'
            '# English\nReturn SHADOW.\n\n'
            '# Python\n```python\ndef compute(context):\n    return "SHADOW"\n```\n'
        )
    return user


def test_library_subdir_indexed_under_its_own_namespace(tmp_path):
    user = _make_two_vault_layout(tmp_path, shadow_present=False)
    reg = SnippetRegistry()
    reg.scan(str(user))
    assert "forge-moda" in reg.loaded_vaults()
    # Authoring namespace doesn't double-index the library snippet
    # (library subdir is pruned from the authoring walk).
    assert reg.get_in_vault("authoring", "leaf") is None
    assert reg.get_in_vault("forge-moda", "leaf") is not None


def test_library_subdir_resolution_order_from_manifest(tmp_path):
    user = _make_two_vault_layout(tmp_path, shadow_present=False)
    reg = SnippetRegistry()
    reg.scan(str(user))
    # `dependencies` in the parent forge.toml drives the resolution order.
    order = reg.resolution_order()
    assert order.index("authoring") < order.index("forge-moda")
    assert order[-1] == "forge"


def test_root_snippet_shadows_library_via_a4(tmp_path):
    user = _make_two_vault_layout(tmp_path, shadow_present=True)
    reg = SnippetRegistry()
    reg.scan(str(user))
    # Bare reference walks A4 order; authoring (the user vault root) wins.
    snippet = reg.get("leaf")
    assert snippet["source"] == "authoring"
    assert snippet["snippet_id"] == "authoring/leaf"


def test_removing_shadow_restores_library_resolution(tmp_path):
    user = _make_two_vault_layout(tmp_path, shadow_present=True)
    reg = SnippetRegistry()
    reg.scan(str(user))
    assert reg.get("leaf")["source"] == "authoring"
    # Delete the shadow and re-scan — library copy becomes the bare-id resolve.
    (user / "leaf.md").unlink()
    reg2 = SnippetRegistry()
    reg2.scan(str(user))
    assert reg2.get("leaf")["source"] == "library"
