"""HTTP-level tests for the unified compute-serialization path.

Closes the asymmetry where /compute used to 500 on ParticleState
returns because serialize_result didn't wire-encode dataclass+ndarray.
After the fix, /compute on any moda snippet returning a ParticleState
yields a `{type: "action", result: {type: "moda_sim_state", content:
{tick, particles: [...]}}, stdout: ...}` envelope — the same content
shape /moda/compute already produces.

The vault used is the real forge-moda library (or its
v0.4.10+ install at one of the candidate paths). Tests skip if no
moda vault is reachable in the env.
"""
import os
from pathlib import Path
import pytest


_VAULT_CANDIDATES = [
    os.environ.get("FORGE_MODA_VAULT_PATH"),
    os.path.expanduser("~/projects/forge-vaults/forge-moda-vault"),
    os.path.expanduser("~/projects/forge-moda"),
]


def _find_moda_vault():
    """Mirrors the candidate list in tests/moda/conftest.py — same
    fallbacks so this test file's discovery doesn't drift from the
    integration suite's."""
    for c in _VAULT_CANDIDATES:
        if c and Path(c, "go.md").is_file() and Path(c, "setup.md").is_file():
            return c
    return None


@pytest.fixture(scope="session")
def moda_vault():
    path = _find_moda_vault()
    if path is None:
        pytest.skip(
            "no moda vault found (set FORGE_MODA_VAULT_PATH or clone "
            "forge-moda alongside forge)"
        )
    return path


def test_compute_simulation_returns_moda_sim_state(client, moda_vault):
    """The new bounded-run simulation snippet (forge-moda v0.4.15+)
    returns ParticleState. Through generic /compute, that now wire-
    encodes as a moda_sim_state-shaped result rather than 500ing in
    JSON encoding."""
    # Some vaults may not have shipped the simulation snippet yet
    # (pre-v0.4.15). Skip cleanly so this test doesn't false-fail.
    if not Path(moda_vault, "simulation.md").is_file():
        pytest.skip("simulation.md not in this vault (pre-v0.4.15 install)")

    client.post("/connect", json={"vault_path": moda_vault})
    resp = client.post("/compute", json={
        "vault_path": moda_vault,
        "snippet_id": "simulation",
        "inputs": {},
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] == "action"

    result = data["result"]
    assert isinstance(result, dict)
    assert result["type"] == "moda_sim_state"
    content = result["content"]
    # 300-tick run advances tick to 300.
    assert content["tick"] == 300
    # setup creates 500 water; sample_clicks adds 50 ink × 3 clicks.
    assert len(content["particles"]) == 500 + 150
    # Each particle is the row-shape the iframe consumes.
    p0 = content["particles"][0]
    assert set(p0.keys()) == {"id", "type", "x", "y", "mass"}


def test_compute_go_returns_moda_sim_state(client, moda_vault):
    """ParticleState recognition is dataclass-keyed, not snippet-
    name-keyed: any snippet returning a ParticleState gets the same
    wire shape. `go` with all-default args (state=None → snapshot
    fallback → sample_state, or prior snapshot when one exists)
    advances one tick.

    Snapshot side-effects: prior /compute calls on `go` or
    `simulation` (e.g. the simulation test running earlier in the
    suite) leave `.forge/edges/authoring/go/...` snapshots in the
    vault, so go reads the latest snapshot rather than
    sample_state on subsequent calls. We don't assert an exact
    tick count here — this test's goal is wire-shape recognition,
    not tick semantics (which test_compute_advances_tick_and_updates_state
    in test_moda.py already covers on an isolated synthetic vault)."""
    client.post("/connect", json={"vault_path": moda_vault})
    resp = client.post("/compute", json={
        "vault_path": moda_vault,
        "snippet_id": "go",
        "inputs": {},
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] == "action"
    result = data["result"]
    assert result["type"] == "moda_sim_state"
    content = result["content"]
    # tick advanced from whatever the snapshot/sample fallback
    # produced (≥0 in any case).
    assert isinstance(content["tick"], int)
    assert content["tick"] >= 1
    # Particles present in row-shape.
    assert len(content["particles"]) > 0
    p0 = content["particles"][0]
    assert set(p0.keys()) == {"id", "type", "x", "y", "mass"}
