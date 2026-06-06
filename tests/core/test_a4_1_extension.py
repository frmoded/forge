"""Tests for the V2a v8 A4.1 extension — Probe 2 (sibling-subdir
resolution within the caller's vault).

Before V2a v8, A4.1 only probed the caller's own subdir for bare
references, then fell through to A4. After v8, between those two
probes, the resolver checks sibling subdirs of the same vault:

  Probe 1 (V2a v5): caller's own dir.        {vault}/{caller_dir}/{bare_id}
  Probe 2 (V2a v8 NEW): vault-sibling dirs.  {vault}/*/{bare_id}, excl. caller_dir
  Probe 3 (A4 fall-through): vault walk.     get_bare(bare_id)

Probe 2 returns the unique match; raises AmbiguousSnippetResolutionError
when two or more sibling subdirs both contain the bare_id. Forge-music
v0.3.9's percussion_lab decomposition is the founding use case —
Murmuration in `forge-music/percussion/` calls `context.compute("solitary")`
which lives in `forge-music/percussion_lab/`.
"""
import os
import tempfile
import pytest
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
from forge.core.graph_resolver import GraphResolver
from forge.core.exceptions import SnippetResolutionError, AmbiguousSnippetResolutionError


def _make_snippet_files(vault_root, vault_name, snippets):
    """Helper: write `snippets` dict (bare_id → body) to disk under
    {vault_root}/{vault_name}/. Each body must be a complete .md
    file with frontmatter (`type: action`). Writes a forge.toml so
    the library-scan path treats the dir as a library vault."""
    vault_dir = os.path.join(vault_root, vault_name)
    os.makedirs(vault_dir, exist_ok=True)
    with open(os.path.join(vault_dir, "forge.toml"), "w") as f:
        f.write(
            f'name = "{vault_name}"\n'
            f'version = "0.0.1"\n'
            f'description = "test fixture for A4.1 Probe 2"\n'
            f'domains = ["test"]\n'
        )
    for bare_id, body in snippets.items():
        target = os.path.join(vault_dir, bare_id + ".md")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write(body)
    return vault_dir


_ACTION_BODY = (
    "---\n"
    "type: action\n"
    "inputs: []\n"
    "---\n"
    "\n"
    "# English\n"
    "\n"
    "noop.\n"
    "\n"
    "# Python\n"
    "\n"
    "```python\n"
    "def compute(context):\n"
    "    return None\n"
    "```\n"
)


def _build_registry(tmpdir, vaults):
    """Build a SnippetRegistry from {vault_name: {bare_id: body}}.
    Materializes each vault as a library subdir under an authoring
    parent (tmpdir/_authoring/) so SnippetRegistry.scan() discovers
    them as library vaults via the forge.toml-presence rule."""
    authoring_root = os.path.join(tmpdir, "_authoring")
    os.makedirs(authoring_root, exist_ok=True)
    for vault_name, snippets in vaults.items():
        _make_snippet_files(authoring_root, vault_name, snippets)
    registry = SnippetRegistry()
    registry.scan(authoring_root)
    return registry


# --- Probe 2 cases (the V2a v8 extension) -----------------------------


def test_probe_1_wins_when_caller_dir_has_the_snippet(tmp_path):
    """If the bare_id exists in the caller's own subdir AND in a
    sibling subdir, Probe 1 returns the caller's own version. Probe 2
    is never consulted."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion/solitary": _ACTION_BODY,        # caller's own dir
            "percussion_lab/solitary": _ACTION_BODY,    # sibling
        },
    })
    resolver = GraphResolver(registry)
    hit = resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")
    assert hit["snippet_id"] == "forge-music/percussion/solitary", (
        f"expected Probe 1 to win; got {hit['snippet_id']}")


def test_probe_2_finds_exactly_one_sibling(tmp_path):
    """The percussion_lab founding case: bare_id only in a sibling
    subdir of the caller's vault → Probe 2 returns it."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion_lab/solitary": _ACTION_BODY,    # sibling only
        },
    })
    resolver = GraphResolver(registry)
    hit = resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")
    assert hit["snippet_id"] == "forge-music/percussion_lab/solitary"


def test_probe_2_raises_ambiguity_for_two_or_more_siblings(tmp_path):
    """Two sibling subdirs each contain the bare_id → resolver raises
    AmbiguousSnippetResolutionError naming ALL candidates so the author
    can qualify."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion_lab/solitary": _ACTION_BODY,
            "percussion_b/solitary": _ACTION_BODY,
        },
    })
    resolver = GraphResolver(registry)
    with pytest.raises(AmbiguousSnippetResolutionError) as exc_info:
        resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")
    err = exc_info.value
    assert err.reference == "solitary"
    # Both candidates surface; order should be deterministic (sorted).
    assert set(err.candidates) == {
        "forge-music/percussion_b/solitary",
        "forge-music/percussion_lab/solitary",
    }
    msg = str(err)
    assert "solitary" in msg
    assert "percussion_b" in msg or "percussion_lab" in msg, (
        f"error message must name candidates: {msg}")


def test_probe_2_falls_through_to_a4_when_no_sibling_matches(tmp_path):
    """No sibling subdir contains the bare_id → Probe 2 yields nothing
    → falls through to A4 → SnippetResolutionError when bare_id is
    unknown anywhere."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion_lab/companions": _ACTION_BODY,
        },
    })
    resolver = GraphResolver(registry)
    with pytest.raises(SnippetResolutionError):
        resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")


def test_probe_2_excludes_caller_own_dir(tmp_path):
    """Probe 2 must NOT find the caller's own dir's snippet (that's
    Probe 1's job). Verifies via a setup where the bare_id only
    exists in the caller's own dir — Probe 1 returns it, Probe 2
    is never consulted but ALSO does not double-count it as a
    sibling. Resolves cleanly to Probe 1's hit."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion/solitary": _ACTION_BODY,
        },
    })
    resolver = GraphResolver(registry)
    hit = resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")
    assert hit["snippet_id"] == "forge-music/percussion/solitary"


def test_probe_2_does_not_cross_vaults(tmp_path):
    """Probe 2 stays within the caller's vault. A bare_id in another
    vault's subdir does NOT match Probe 2 — verified by setting up
    `solitary` ONLY in `forge-moda/percussion_lab/` (a different vault
    from the caller's `forge-music`). Probe 2 yields no candidates;
    A4 fall-through's `get_bare` walks vault roots only (not subdir
    contents) so it also misses. Final result: SnippetResolutionError.

    The intent: enforce the "Don't make Probe 2 probe across vaults"
    constraint from prompt §Don'ts."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
        },
        "forge-moda": {
            "percussion_lab/solitary": _ACTION_BODY,    # cross-vault, subdir
        },
    })
    resolver = GraphResolver(registry)
    registry.set_resolution_order([AUTHORING_VAULT, "forge-moda", "forge-music"])
    # Bare lookup ONLY finds vault-root entries via A4 walk; subdir
    # entries in other vaults are NOT reachable bare. Probe 2 is
    # caller-vault-only. So nothing resolves — SnippetResolutionError.
    with pytest.raises(SnippetResolutionError):
        resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")


def test_qualified_reference_skips_probes_entirely(tmp_path):
    """Caller passes a qualified ID (already has `/`). The resolver's
    qualified branch fires; Probes 1 + 2 are not consulted."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion_lab/solitary": _ACTION_BODY,
            "percussion/solitary": _ACTION_BODY,
        },
    })
    resolver = GraphResolver(registry)
    # Caller passes `forge-music/percussion_lab/solitary` qualified —
    # must resolve to that exact path, not Probe 1's caller-dir hit.
    hit = resolver.resolve(
        "forge-music/percussion_lab/solitary",
        caller_id="forge-music/percussion/murmuration",
    )
    assert hit["snippet_id"] == "forge-music/percussion_lab/solitary"


def test_resolution_is_idempotent(tmp_path):
    """Same bare_id resolved twice from the same caller yields the
    same snippet — defensive against any mutable state in the probe
    chain."""
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion_lab/solitary": _ACTION_BODY,
        },
    })
    resolver = GraphResolver(registry)
    a = resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")
    b = resolver.resolve("solitary", caller_id="forge-music/percussion/murmuration")
    assert a["snippet_id"] == b["snippet_id"]


def test_forge_music_v0_3_9_percussion_lab_integration(tmp_path):
    """Production-shape regression: bare reference shape that
    forge-music v0.3.9 (commit 489ce7d) cannot ship to cohort vaults
    until this resolver extension lands. Murmuration's Python facet
    contains `context.compute("solitary")` and `context.compute("companions")`
    etc. — these MUST resolve to the corresponding `percussion_lab/*`
    snippets when the caller is `forge-music/percussion/murmuration`.

    Validates the founding use case end-to-end."""
    # Mirror v0.3.9's actual layout: percussion/murmuration + percussion_lab/
    # eight section snippets.
    registry = _build_registry(str(tmp_path), {
        "forge-music": {
            "percussion/murmuration": _ACTION_BODY,
            "percussion_lab/solitary": _ACTION_BODY,
            "percussion_lab/companions": _ACTION_BODY,
            "percussion_lab/gathering": _ACTION_BODY,
            "percussion_lab/swarming": _ACTION_BODY,
            "percussion_lab/peak": _ACTION_BODY,
            "percussion_lab/dispersing": _ACTION_BODY,
            "percussion_lab/threading": _ACTION_BODY,
            "percussion_lab/resting": _ACTION_BODY,
        },
    })
    resolver = GraphResolver(registry)
    caller = "forge-music/percussion/murmuration"
    for section in ("solitary", "companions", "gathering", "swarming",
                    "peak", "dispersing", "threading", "resting"):
        hit = resolver.resolve(section, caller_id=caller)
        assert hit["snippet_id"] == f"forge-music/percussion_lab/{section}", (
            f"section {section!r} failed to resolve via Probe 2")
