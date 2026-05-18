"""Shared fixtures for the 25-block MoDa partition.

The moda block snippets live in a sibling vault (the authoring vault the
backend's FORGE_MODA_VAULT_PATH defaults to, or the promoted
distributable). They are not part of the forge package, so these tests
resolve them through the same registry/resolver machinery the backend
uses and skip the whole partition if no vault is reachable (fresh
clone / CI without the sibling repo).
"""
import os
from pathlib import Path

import numpy as np
import pytest

from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import extract_python, exec_python
from forge.moda.types import ParticleState

_CANDIDATES = [
    os.environ.get("FORGE_MODA_VAULT_PATH"),
    os.path.expanduser("~/projects/forge-vaults/forge-moda-vault"),
    os.path.expanduser("~/projects/forge-moda"),
]


def _find_vault():
    for c in _CANDIDATES:
        if c and Path(c, "go.md").is_file() and Path(c, "setup.md").is_file():
            return c
    return None


@pytest.fixture(scope="session")
def moda_vault():
    path = _find_vault()
    if path is None:
        pytest.skip(
            "no moda vault found (set FORGE_MODA_VAULT_PATH or clone "
            "forge-moda alongside forge)"
        )
    return path


@pytest.fixture(scope="session")
def resolver(moda_vault):
    reg = SnippetRegistry()
    reg.scan(moda_vault)
    return GraphResolver(reg), reg, moda_vault


@pytest.fixture(scope="session")
def run_block(resolver):
    res, reg, vault = resolver

    def _run(snippet_id, *args, **inputs):
        snip = res.resolve(snippet_id)
        code = extract_python(snip["body"])
        _, result = exec_python(
            code, inputs, res, args=args,
            vault_path=vault, registry=reg, snippet_id=snip["snippet_id"],
        )
        return result

    return _run


@pytest.fixture(scope="session")
def block_source(resolver):
    res, _reg, _vault = resolver

    def _src(snippet_id):
        return extract_python(res.resolve(snippet_id)["body"])

    return _src


def make_state(
    *,
    n_water=0,
    n_ink=0,
    width=800.0,
    height=600.0,
    tick=0,
    water_speed=50.0,
    ink_speed=50.0,
    seed=0,
):
    """Hand-crafted struct-of-arrays ParticleState for integration tests.

    Water rows first (ids 0..n_water-1), then ink (continuing ids).
    Positions are spread deterministically inside the chamber; headings
    are a fixed sweep so collision/bounce assertions are reproducible.
    """
    rng = np.random.default_rng(seed)
    n = n_water + n_ink
    ids = np.arange(n, dtype=np.int64)
    types = np.array(["water"] * n_water + ["ink"] * n_ink, dtype=object)
    xs = rng.uniform(10, width - 10, n).astype(np.float64)
    ys = rng.uniform(10, height - 10, n).astype(np.float64)
    headings = (np.linspace(0.0, 2 * np.pi, n, endpoint=False)
                if n else np.array([], dtype=np.float64))
    speeds = np.array([water_speed] * n_water + [ink_speed] * n_ink,
                      dtype=np.float64)
    masses = np.array(["medium"] * n, dtype=object)
    return ParticleState(
        tick=tick, ids=ids, types=types, xs=xs, ys=ys,
        headings=headings, speeds=speeds, masses=masses,
        width=width, height=height,
    )
