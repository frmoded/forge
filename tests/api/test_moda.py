"""Tests for the /moda/* router.

The router runs Forge against the vault at FORGE_MODA_VAULT_PATH. The
tests build a minimal two-snippet vault under tmp_path and monkeypatch
the module-level constant — the production forge-moda vault isn't a
dependency.
"""
import os
import pytest
from fastapi.testclient import TestClient

from forge.api import moda
from forge.api.server import app, _manager


_CONFIG_MD = """---
type: data
content_type: json
read_only: true
description: test scenario config
---

```json
{"count": 5, "width": 100, "height": 100}
```
"""


# Post-scenario-cleanup minimal test setup: builds the new arrays-first
# ParticleState shape directly. /moda/init no longer threads a scenarioId,
# so the setup snippet takes only `context`. The test vault's only data
# snippet remains `config` — the setup just reads it unconditionally.
_SETUP_MD = """---
type: action
inputs: []
description: minimal test setup
---

# English

Read the [[config]] scenario and build the initial state.

# Python

```python
def compute(context):
    cfg = context.compute("config")
    n = cfg["count"]
    ids = numpy.arange(n, dtype=numpy.int64)
    types = numpy.full(n, 'water', dtype=object)
    xs = numpy.arange(n, dtype=numpy.float64) * 10.0
    ys = numpy.arange(n, dtype=numpy.float64) * 10.0
    headings = numpy.zeros(n, dtype=numpy.float64)
    speeds = numpy.full(n, 10.0, dtype=numpy.float64)
    masses = numpy.full(n, 'medium', dtype=object)
    return ParticleState(
        tick=0,
        ids=ids, types=types, xs=xs, ys=ys,
        headings=headings, speeds=speeds, masses=masses,
        width=float(cfg["width"]), height=float(cfg["height"]),
    )
```
"""

# Minimal test on_click: /moda/click runs the on_click snippet (Phase 4+),
# so the test vault needs one. This one is a no-op that returns the state
# unchanged — the test only asserts the wire ack, not any state mutation.
_ON_CLICK_MD = """---
type: action
inputs:
  - state
  - x
  - y
description: minimal test on_click — no-op
---

# English

Return `state` unchanged.

# Python

```python
def compute(context, state, x, y):
    return state
```
"""


# Phase-7 minimal test go: accepts the (state, dt, temperature) signature
# /moda/compute now produces. The temperature parameter is accepted but
# ignored — this test is about the tick-advance + wire-shape contract,
# not the temperature coupling that the production go encapsulates.
_GO_MD = """---
type: action
inputs:
  - state
  - dt
  - temperature
description: advance one tick by shifting x by 1
---

# English

Shift each particle's x by 1.

# Python

```python
def compute(context, state, dt, temperature):
    new_xs = state.xs + 1.0
    return ParticleState(
        tick=state.tick + 1,
        ids=state.ids,
        types=state.types,
        xs=new_xs,
        ys=state.ys,
        headings=state.headings,
        speeds=state.speeds,
        masses=state.masses,
        width=state.width,
        height=state.height,
    )
```
"""


@pytest.fixture
def moda_vault(tmp_path):
  (tmp_path / "forge.toml").write_text(
    'name = "test-moda"\nversion = "0.0.0"\ndescription = "test"\n')
  (tmp_path / "config.md").write_text(_CONFIG_MD)
  (tmp_path / "setup.md").write_text(_SETUP_MD)
  (tmp_path / "go.md").write_text(_GO_MD)
  (tmp_path / "on_click.md").write_text(_ON_CLICK_MD)
  return str(tmp_path)


@pytest.fixture(autouse=True)
def point_moda_at_vault(monkeypatch, moda_vault):
  monkeypatch.setattr(moda, "FORGE_MODA_VAULT_PATH", moda_vault)
  # The router uses the server's shared session manager. Wipe it so we
  # don't see cached state from another test's vault.
  _manager.clear()
  # Also wipe the in-process session store between tests.
  moda.SESSIONS.clear()
  yield
  _manager.clear()
  moda.SESSIONS.clear()


@pytest.fixture
def client():
  return TestClient(app)


# ---------------------------------------------------------------------------
# /moda/init
# ---------------------------------------------------------------------------

def test_init_returns_session_state_and_config(client):
  resp = client.post("/moda/init", json={})
  assert resp.status_code == 200
  data = resp.json()
  assert isinstance(data["sessionId"], str) and len(data["sessionId"]) == 32
  assert data["state"]["tick"] == 0
  assert len(data["state"]["particles"]) == 5
  assert data["config"] == {
    "width": 100,
    "height": 100,
    "temperatureLevels": ["zero", "low", "medium", "high"],
  }


def test_init_wire_particle_strips_internal_fields(client):
  resp = client.post("/moda/init", json={})
  p = resp.json()["state"]["particles"][0]
  # The wire shape carries only the public fields. heading/speed are
  # internal to the simulation and never leave the backend.
  assert set(p.keys()) == {"id", "type", "x", "y", "mass"}


def test_init_captures_edges_under_qualified_caller_id(client, moda_vault):
  """Regression test: bare-id captures (e.g. .forge/edges/setup/...) used
  to leave the plugin's edges panel showing 0 outgoing because it queries
  under the qualified `authoring/<id>` namespace. Setup → config is the
  only edge in this minimal vault, but that's enough to validate the
  path format.
  """
  client.post("/moda/init", json={})

  edges_root = os.path.join(moda_vault, ".forge", "edges")
  assert os.path.isdir(edges_root), \
    "setup → config edge should have been captured on /moda/init"

  # Path must be .forge/edges/authoring/setup/authoring/config.md — both
  # caller and callee in the qualified `authoring/<id>` form.
  expected = os.path.join(
    edges_root, "authoring", "setup", "authoring", "config.md")
  assert os.path.isfile(expected), (
    f"expected qualified edge path {expected!r} not found; "
    f"got tree: {os.listdir(edges_root)}")


# ---------------------------------------------------------------------------
# /moda/compute
# ---------------------------------------------------------------------------

def test_compute_advances_tick_and_updates_state(client):
  init = client.post("/moda/init", json={}).json()
  sid = init["sessionId"]
  x0 = init["state"]["particles"][0]["x"]

  r1 = client.post(
    "/moda/compute",
    json={"sessionId": sid, "dt": 0.0333, "temperature": "medium"},
  )
  assert r1.status_code == 200
  s1 = r1.json()["state"]
  assert s1["tick"] == 1
  assert s1["particles"][0]["x"] == pytest.approx(x0 + 1.0)

  # Tick again — the SESSIONS store carries forward the updated state.
  r2 = client.post(
    "/moda/compute",
    json={"sessionId": sid, "dt": 0.0333, "temperature": "medium"},
  )
  assert r2.json()["state"]["tick"] == 2
  assert r2.json()["state"]["particles"][0]["x"] == pytest.approx(x0 + 2.0)


def test_compute_unknown_session_returns_404(client):
  resp = client.post(
    "/moda/compute",
    json={"sessionId": "deadbeef" * 4, "dt": 0.0333, "temperature": "medium"},
  )
  assert resp.status_code == 404
  assert "deadbeef" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /moda/click
# ---------------------------------------------------------------------------

def test_click_acks_for_known_session(client):
  init = client.post("/moda/init", json={}).json()
  resp = client.post(
    "/moda/click",
    json={"sessionId": init["sessionId"], "x": 50.0, "y": 50.0},
  )
  assert resp.status_code == 200
  assert resp.json() == {"ack": True}


def test_click_unknown_session_returns_404(client):
  resp = client.post(
    "/moda/click",
    json={"sessionId": "nope", "x": 1.0, "y": 2.0},
  )
  assert resp.status_code == 404
