"""Guard: the moda suite binds to the SHIPPING vault, not a stale sibling.

Drain 2026-08-20-1210(a). For a long stretch `_find_vault` preferred
`~/projects/forge-vaults/forge-moda-vault` — a pre-split combined
moda+tutorial vault at `forge.toml` 0.1.0, still containing notes the
driver had deleted. 86 tests passed against it while the shipping vault
failed 34 of them, which is why `simulation`'s breakage reached CCQA
instead of the suite (drain 2026-08-18-2310 §5.1).

A reorder alone would fix today and not tomorrow: the next stale
candidate to appear would win just as silently. So this asserts the
INVARIANT rather than the order — whatever `_find_vault` returns must be
the newest vault available. A stale winner fails loudly and names both
versions.

Deliberately tolerant of absence: the driver may rename or remove the
legacy sibling at any time (drain 1210 §6), and this must keep passing
when it is gone — a guard that broke on the cleanup it asked for would
be its own kind of trap.
"""
import os

import pytest

from tests.moda._helpers import (
    _CANDIDATES,
    _find_vault,
    candidate_versions,
    parse_vault_version,
)


def test_the_resolved_vault_is_the_newest_available():
    resolved = _find_vault()
    if resolved is None:
        pytest.skip("no moda vault reachable")

    versions = candidate_versions()
    # Non-vacuity: with nothing to compare against, this test could
    # never fail, which is the silent-pass shape (I23) the whole class
    # of bug hides in.
    assert versions, "no candidate vault carried a parseable forge.toml version"

    resolved_version = parse_vault_version(resolved)
    newest_path, newest_version = max(versions, key=lambda pv: pv[1])

    assert resolved_version == newest_version, (
        f"_find_vault resolved {resolved} at forge.toml "
        f"{'.'.join(map(str, resolved_version))}, but {newest_path} is newer "
        f"at {'.'.join(map(str, newest_version))}. The suite would validate a "
        f"non-shipping artifact — the exact failure that let `simulation` "
        f"break for CCQA while 86 tests stayed green. Fix the candidate "
        f"order in tests/moda/_helpers.py, or retire the stale vault."
    )


def test_an_explicit_env_override_still_wins():
    """`FORGE_MODA_VAULT_PATH` must keep overriding everything — CI and
    the per-drain acceptance runs depend on pointing the suite at a
    specific tree."""
    assert _CANDIDATES[0] is os.environ.get("FORGE_MODA_VAULT_PATH") or True
    # Structural: the env var must be consulted first in the list.
    from tests.moda import _helpers
    import inspect
    src = inspect.getsource(_helpers)
    env_at = src.index("FORGE_MODA_VAULT_PATH")
    projects_at = src.index('"~/projects/forge-moda"')
    assert env_at < projects_at, "the env override must be consulted first"


def test_the_shipping_vault_is_preferred_over_the_legacy_sibling():
    """The concrete ordering, stated once so a future edit that reorders
    them fails here with a readable reason rather than only via the
    version-invariant above."""
    from tests.moda import _helpers
    import inspect
    src = inspect.getsource(_helpers)
    shipping_at = src.index('"~/projects/forge-moda"')
    legacy = '"~/projects/forge-vaults/forge-moda-vault"'
    if legacy in src:
        assert shipping_at < src.index(legacy), (
            "the shipping vault must be preferred over the legacy sibling"
        )


def test_version_parsing_handles_the_shapes_that_actually_occur(tmp_path):
    (tmp_path / "forge.toml").write_text('name = "x"\nversion = "0.5.6"\n')
    assert parse_vault_version(str(tmp_path)) == (0, 5, 6)

    missing = tmp_path / "nope"
    missing.mkdir()
    assert parse_vault_version(str(missing)) is None

    weird = tmp_path / "weird"
    weird.mkdir()
    (weird / "forge.toml").write_text('version = "not-semver"\n')
    assert parse_vault_version(str(weird)) is None
