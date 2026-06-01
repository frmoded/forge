"""Tests for v0.2.26 caller-scoped bare-reference resolution.

When a snippet inside a library-vault subdir (e.g. `forge-music/blues/song`)
issues a bare reference like `context.compute("chorus")`, the resolver
should probe the caller's own directory FIRST — so the lookup tries
`forge-music/blues/chorus` before falling back to the legacy vault-walk
on bare keys. This makes "siblings-in-same-dir" the natural reference
shape from inside subdir snippets and matches what snippet authors
intuitively expect.

The probe is TRY-FIRST, not TRY-ONLY: misses still fall through to
`registry.get_bare(snippet_id)`, preserving the existing
resolution-order contract for callers without a `caller_id`.
"""

import pytest

from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
from forge.core.graph_resolver import GraphResolver
from forge.core.executor import exec_python
from forge.core.exceptions import SnippetResolutionError


def _seed_library(
  registry: SnippetRegistry,
  vault_name: str,
  bare_id: str,
  marker: str,
  body: str = "",
) -> None:
  registry._vaults.setdefault(vault_name, {})
  registry._vaults[vault_name][bare_id] = {
    "meta": {"type": "action", "marker": marker},
    "body": body,
    "path": f"/lib/{vault_name}/{bare_id}.md",
    "vault": vault_name,
    "vault_path": f"/lib/{vault_name}",
    "source": "library",
    "snippet_id": f"{vault_name}/{bare_id}",
  }


def _make_registry_with_blues() -> SnippetRegistry:
  """Build a registry mirroring forge-music post-v0.3.1: top-level
  `form` + `twelve_bar_blues_progression`, plus `blues/` subdir with
  `form`, `chorus`, `song`, `solo_chorus`."""
  registry = SnippetRegistry()
  _seed_library(registry, "forge-music", "form", marker="top-level-form")
  _seed_library(
    registry, "forge-music", "twelve_bar_blues_progression",
    marker="top-level-12bar",
  )
  _seed_library(registry, "forge-music", "blues/form", marker="blues-form")
  _seed_library(registry, "forge-music", "blues/chorus", marker="blues-chorus")
  _seed_library(registry, "forge-music", "blues/song", marker="blues-song")
  _seed_library(
    registry, "forge-music", "blues/solo_chorus", marker="blues-solo",
  )
  registry.set_resolution_order([AUTHORING_VAULT, "forge-music"])
  return registry


def test_bare_in_caller_dir_wins_over_top_level_when_caller_qualified():
  """`form` from inside `forge-music/blues/song` should resolve to
  `forge-music/blues/form`, NOT top-level `forge-music/form`."""
  registry = _make_registry_with_blues()
  resolver = GraphResolver(registry)

  hit = resolver.resolve("form", caller_id="forge-music/blues/song")

  assert hit["snippet_id"] == "forge-music/blues/form"
  assert hit["meta"]["marker"] == "blues-form"


def test_bare_resolves_sibling_when_caller_in_subdir():
  """The prod case: `context.compute("chorus")` inside `blues/song`
  resolves to `blues/chorus` rather than missing all vaults."""
  registry = _make_registry_with_blues()
  resolver = GraphResolver(registry)

  hit = resolver.resolve("chorus", caller_id="forge-music/blues/song")

  assert hit["snippet_id"] == "forge-music/blues/chorus"
  assert hit["meta"]["marker"] == "blues-chorus"


def test_bare_falls_back_to_resolution_order_when_no_sibling():
  """Sibling-scoped probe is TRY-FIRST, not TRY-ONLY. Misses fall
  through to the legacy bare walk, which here also misses, raising."""
  registry = _make_registry_with_blues()
  resolver = GraphResolver(registry)

  with pytest.raises(SnippetResolutionError) as exc:
    resolver.resolve("noop", caller_id="forge-music/blues/song")

  assert "forge-music" in exc.value.searched


def test_bare_without_caller_id_preserves_legacy_resolution():
  """Pre-fix behavior must remain byte-identical for callers that
  don't pass caller_id — that's HTTP /compute, moda dispatch, etc."""
  registry = _make_registry_with_blues()
  resolver = GraphResolver(registry)

  hit = resolver.resolve("form")

  assert hit["snippet_id"] == "forge-music/form"
  assert hit["meta"]["marker"] == "top-level-form"


def test_qualified_id_ignores_caller_id():
  """A qualified `vault/bare` reference is absolute; caller scope
  shouldn't subvert it."""
  registry = _make_registry_with_blues()
  resolver = GraphResolver(registry)

  hit = resolver.resolve(
    "forge-music/form", caller_id="forge-music/blues/song",
  )

  assert hit["snippet_id"] == "forge-music/form"
  assert hit["meta"]["marker"] == "top-level-form"


def test_caller_at_top_level_uses_legacy_bare_walk():
  """When the caller has no subdir component (caller_id =
  `forge-music/song`, hypothetical top-level `song`), the sibling
  probe is skipped — there's no caller-dir to scope to. Legacy walk
  returns the top-level `form`."""
  registry = _make_registry_with_blues()
  # No actual `forge-music/song` registered, but caller_id semantics
  # are about the string shape, not whether the caller exists in
  # the registry.
  resolver = GraphResolver(registry)

  hit = resolver.resolve("form", caller_id="forge-music/song")

  assert hit["snippet_id"] == "forge-music/form"
  assert hit["meta"]["marker"] == "top-level-form"


def test_context_compute_threads_caller_id_through():
  """End-to-end seam test: `ForgeContext.compute` should pass its
  internal `_caller_id` into `resolver.resolve` so a `context.compute(
  "child")` call from inside `forge-music/blues/parent.md` lands on
  `forge-music/blues/child` rather than missing."""
  registry = SnippetRegistry()
  parent_body = (
    "# Python\n\n"
    "```python\n"
    "def compute(context):\n"
    "    return context.compute('child')\n"
    "```\n"
  )
  child_body = (
    "# Python\n\n"
    "```python\n"
    "def compute(context):\n"
    "    return 42\n"
    "```\n"
  )
  _seed_library(
    registry, "forge-music", "blues/parent",
    marker="parent", body=parent_body,
  )
  _seed_library(
    registry, "forge-music", "blues/child",
    marker="child", body=child_body,
  )
  registry.set_resolution_order([AUTHORING_VAULT, "forge-music"])
  resolver = GraphResolver(registry)

  parent_code = (
    "def compute(context):\n"
    "    return context.compute('child')\n"
  )

  _stdout, result = exec_python(
    parent_code, {}, resolver,
    snippet_id="forge-music/blues/parent",
    registry=registry,
  )

  assert result == 42
