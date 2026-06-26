"""Shared fixtures for the forge-music sanity tests.

The music snippets live in a sibling vault (`~/projects/forge-music/`,
the published source-of-truth). They aren't part of the forge package,
so these tests resolve them through the same registry/resolver
machinery the engine's compute path uses, and skip the whole partition
if no vault is reachable (fresh clone / CI without the sibling repo).

Plain helpers (`_find_vault`) live in `_helpers.py`; fixtures stay
here. Mirrors the moda partition's layout.
"""
import pytest

from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import resolve_action_code, exec_python

from tests.music._helpers import _find_vault


@pytest.fixture(scope="session")
def music_vault():
    path = _find_vault()
    if path is None:
        pytest.skip(
            "no forge-music vault found (set FORGE_MUSIC_VAULT_PATH or "
            "clone forge-music alongside forge)"
        )
    return path


@pytest.fixture(scope="session")
def music_resolver(music_vault):
    reg = SnippetRegistry()
    reg.scan(music_vault)
    return GraphResolver(reg), reg, music_vault


@pytest.fixture(scope="session")
def run_music_block(music_resolver):
    res, reg, vault = music_resolver

    def _run(snippet_id, *args, **inputs):
        snip = res.resolve(snippet_id)
        # Use resolve_action_code so V2 notes (# E-- heading) get parsed
        # + transpiled via forge.recipe. V1 notes (# Python or
        # # English heading) fall through to the legacy path unchanged.
        code = resolve_action_code(snip)
        _, result = exec_python(
            code, inputs, res, args=args,
            vault_path=vault, registry=reg, snippet_id=snip["snippet_id"],
            domains=["music"],
        )
        return result

    return _run
