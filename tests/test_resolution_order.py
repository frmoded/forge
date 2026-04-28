import pytest
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT, BUILTIN_VAULT
from forge.core.graph_resolver import GraphResolver
from forge.core.exceptions import SnippetResolutionError


def _make_builtin(snippet_id: str, marker: str = "builtin") -> dict:
  return {
    "meta": {"type": "action", "marker": marker},
    "body": f"# Python\n\n```python\ndef run(context):\n  return '{marker}'\n```\n",
    "path": "/builtins/x.md",
    "vault": "forge",
    "source": "builtin",
    "snippet_id": snippet_id,
  }


def _seed_authoring(registry: SnippetRegistry, bare_id: str, marker: str = "authoring") -> None:
  """Inject a synthetic authoring snippet directly into the registry's internal storage.

  Avoids touching the filesystem; the tests are about resolution semantics.
  """
  registry._vaults.setdefault(AUTHORING_VAULT, {})
  registry._vaults[AUTHORING_VAULT][bare_id] = {
    "meta": {"type": "action", "marker": marker},
    "body": "",
    "path": f"/authoring/{bare_id}.md",
    "vault": AUTHORING_VAULT,
    "source": "authoring",
    "snippet_id": f"{AUTHORING_VAULT}/{bare_id}",
  }


def _seed_library(registry: SnippetRegistry, vault_name: str, bare_id: str, marker: str) -> None:
  registry._vaults.setdefault(vault_name, {})
  registry._vaults[vault_name][bare_id] = {
    "meta": {"type": "action", "marker": marker},
    "body": "",
    "path": f"/lib/{vault_name}/{bare_id}.md",
    "vault": vault_name,
    "source": "library",
    "snippet_id": f"{vault_name}/{bare_id}",
  }


def test_bare_resolves_to_authoring_first():
  registry = SnippetRegistry()
  _seed_authoring(registry, "install", marker="from-authoring")
  registry.register_builtin_vault([_make_builtin("forge/install", marker="from-builtin")])
  resolver = GraphResolver(registry)

  hit = resolver.resolve("install")
  assert hit["meta"]["marker"] == "from-authoring"
  assert hit["vault"] == AUTHORING_VAULT


def test_bare_falls_through_to_builtin():
  registry = SnippetRegistry()
  registry.register_builtin_vault([_make_builtin("forge/install")])
  resolver = GraphResolver(registry)

  hit = resolver.resolve("install")
  assert hit["vault"] == BUILTIN_VAULT


def test_qualified_forge_bypasses_authoring_override():
  registry = SnippetRegistry()
  _seed_authoring(registry, "install", marker="user-override")
  registry.register_builtin_vault([_make_builtin("forge/install", marker="real-builtin")])
  resolver = GraphResolver(registry)

  hit = resolver.resolve("forge/install")
  assert hit["meta"]["marker"] == "real-builtin"
  assert hit["vault"] == BUILTIN_VAULT


def test_qualified_authoring_works():
  registry = SnippetRegistry()
  _seed_authoring(registry, "hello", marker="from-authoring")
  resolver = GraphResolver(registry)

  hit = resolver.resolve("authoring/hello")
  assert hit["meta"]["marker"] == "from-authoring"


def test_qualified_unknown_vault_raises():
  registry = SnippetRegistry()
  resolver = GraphResolver(registry)
  with pytest.raises(SnippetResolutionError) as exc:
    resolver.resolve("unknown-vault/something")
  assert exc.value.searched == ["unknown-vault"]


def test_bare_miss_raises_with_searched_sources():
  registry = SnippetRegistry()
  registry.register_builtin_vault([_make_builtin("forge/install")])
  resolver = GraphResolver(registry)

  with pytest.raises(SnippetResolutionError) as exc:
    resolver.resolve("not-a-snippet")
  assert "authoring" in exc.value.searched
  assert "forge (built-in)" in exc.value.searched


def test_library_order_respected():
  registry = SnippetRegistry()
  _seed_library(registry, "lib-a", "shared", "from-a")
  _seed_library(registry, "lib-b", "shared", "from-b")
  registry.set_resolution_order([AUTHORING_VAULT, "lib-a", "lib-b"])
  resolver = GraphResolver(registry)

  hit = resolver.resolve("shared")
  assert hit["meta"]["marker"] == "from-a"


def test_set_resolution_order_appends_builtin_if_missing():
  registry = SnippetRegistry()
  registry.set_resolution_order([AUTHORING_VAULT, "lib-a"])
  assert registry.resolution_order()[-1] == BUILTIN_VAULT


def test_set_resolution_order_dedupes_builtin():
  registry = SnippetRegistry()
  registry.set_resolution_order([AUTHORING_VAULT, BUILTIN_VAULT, "lib-a"])
  order = registry.resolution_order()
  assert order.count(BUILTIN_VAULT) == 1
  assert order[-1] == BUILTIN_VAULT


def test_qualified_reference_does_not_walk_order():
  """A qualified reference must NOT fall through to other vaults on miss."""
  registry = SnippetRegistry()
  _seed_authoring(registry, "install")
  registry.register_builtin_vault([_make_builtin("forge/other")])
  resolver = GraphResolver(registry)

  with pytest.raises(SnippetResolutionError):
    resolver.resolve("forge/install")  # exists in authoring as bare, not in forge


def test_register_builtin_vault_replaces_previous():
  registry = SnippetRegistry()
  registry.register_builtin_vault([_make_builtin("forge/v1")])
  registry.register_builtin_vault([_make_builtin("forge/v2")])

  resolver = GraphResolver(registry)
  with pytest.raises(SnippetResolutionError):
    resolver.resolve("forge/v1")
  assert resolver.resolve("forge/v2")["snippet_id"] == "forge/v2"


def test_register_builtin_vault_rejects_wrong_namespace():
  registry = SnippetRegistry()
  bad = _make_builtin("notforge/install")
  bad["vault"] = "notforge"
  with pytest.raises(ValueError):
    registry.register_builtin_vault([bad])


def test_try_resolve_returns_none_on_miss():
  registry = SnippetRegistry()
  resolver = GraphResolver(registry)
  assert resolver.try_resolve("nope") is None


def test_resolution_error_message_format():
  registry = SnippetRegistry()
  registry.register_builtin_vault([_make_builtin("forge/x")])
  resolver = GraphResolver(registry)
  try:
    resolver.resolve("missing")
  except SnippetResolutionError as e:
    assert "Snippet 'missing' not found" in str(e)
    assert "Searched:" in str(e)
    assert "forge (built-in)" in str(e)
