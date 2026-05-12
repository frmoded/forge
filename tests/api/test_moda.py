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


_SETUP_MD = """---
type: action
description: minimal test setup
---

# English

Read the [[config]] scenario and build the initial state.

# Python

```python
def compute(context):
    cfg = context.compute("config")
    particles = [
        Particle(id=i, type='water', x=float(i * 10), y=float(i * 10),
                 heading=0.0, speed=10.0, mass='medium')
        for i in range(cfg["count"])
    ]
    return ParticleState(tick=0, particles=particles,
                         width=float(cfg["width"]), height=float(cfg["height"]))
```
"""

_GO_MD = """---
type: action
inputs:
  - state
  - dt
description: advance one tick by shifting x by 1
---

# English

Shift each particle's x by 1.

# Python

```python
def compute(context, state, dt):
    moved = [
        Particle(id=p.id, type=p.type, x=p.x + 1.0, y=p.y,
                 heading=p.heading, speed=p.speed, mass=p.mass)
        for p in state.particles
    ]
    return ParticleState(tick=state.tick + 1, particles=moved,
                         width=state.width, height=state.height)
```
"""


@pytest.fixture
def moda_vault(tmp_path):
  (tmp_path / "forge.toml").write_text(
    'name = "test-moda"\nversion = "0.0.0"\ndescription = "test"\n')
  (tmp_path / "config.md").write_text(_CONFIG_MD)
  (tmp_path / "setup.md").write_text(_SETUP_MD)
  (tmp_path / "go.md").write_text(_GO_MD)
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
  resp = client.post("/moda/init", json={"scenarioId": "default_diffusion"})
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
  resp = client.post("/moda/init", json={"scenarioId": "default_diffusion"})
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
  client.post("/moda/init", json={"scenarioId": "default_diffusion"})

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
  init = client.post("/moda/init", json={"scenarioId": "default_diffusion"}).json()
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
  init = client.post("/moda/init", json={"scenarioId": "default_diffusion"}).json()
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
