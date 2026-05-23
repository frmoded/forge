"""Plain (non-fixture) helpers for the moda integration tests.

Conftest is the right home for pytest fixtures (anything decorated with
`@pytest.fixture`); plain Python helpers belong in a sibling module so
test files can import them by name without the `from tests.moda.conftest
import ...` indirection (which also required a package marker on the
tests/ tree).

Holds:
- `_find_vault()`: locate the moda authoring/distributable vault by
  walking a candidate list; returns None when no vault is reachable
  (fresh clone / CI without the sibling repo). The `moda_vault`
  fixture in conftest.py also calls this — once for the fixture's
  skip-or-return decision.
- `make_state(...)`: deterministic ParticleState builder used by
  chain-integration assertions (water then ink rows, parallel arrays,
  reproducible headings + spreads).
"""
import os
from pathlib import Path

import numpy as np

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
