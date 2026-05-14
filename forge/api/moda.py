"""forge-moda router: /moda/init, /moda/compute, /moda/click.

Phase 1 hooks /moda/init up to Forge — it resolves and runs the
`setup` snippet from the forge-moda vault, stores the resulting
ParticleState in SESSIONS, and serializes the wire shape (dropping
internal `heading` and `speed` fields).

/moda/compute stays as an echo for this phase; Phase 2 wires it to
the `go` snippet. /moda/click stays as ack-only (Phase 4).

Wire format is camelCase JSON; Pydantic uses snake_case attributes
with explicit aliases so the Python side reads idiomatic.
"""

import logging
import os
import time
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

from forge.core.executor import extract_python, exec_python, SnippetExecError, read_data_snippet
from forge.core.exceptions import SnippetResolutionError


# Vault path the simulator invokes Forge against. Default points at the
# authoring vault during development so edits, /moda runs, and edge
# snapshots all happen in the same place a snippet author is looking
# at — without it, runtime captures land in forge-moda/.forge and the
# edges panel for the authoring file stays empty.
#
# For shipped builds, set FORGE_MODA_VAULT_PATH=~/projects/forge-moda
# (the distributable). The env-var is read once at process start, so a
# uvicorn restart is needed after changing it.
FORGE_MODA_VAULT_PATH = os.environ.get(
  "FORGE_MODA_VAULT_PATH",
  os.path.expanduser("~/projects/forge-vaults/forge-moda-vault"),
)


Temperature = Literal["zero", "low", "medium", "high"]
ParticleType = Literal["water", "ink"]
ParticleMass = Literal["light", "medium", "heavy"]


class _CamelModel(BaseModel):
  # Accept both alias (camelCase, on the wire) and field name (snake_case,
  # in Python). model_dump(by_alias=True) is what serializes to the wire.
  model_config = ConfigDict(populate_by_name=True)


class Particle(_CamelModel):
  id: int
  type: ParticleType
  x: float
  y: float
  mass: ParticleMass


class SimState(_CamelModel):
  tick: int
  particles: list[Particle]


class Config(_CamelModel):
  width: int
  height: int
  temperature_levels: list[Temperature] = Field(alias="temperatureLevels")


class InitRequest(_CamelModel):
  scenario_id: str = Field(alias="scenarioId")


class InitResponse(_CamelModel):
  session_id: str = Field(alias="sessionId")
  state: SimState
  config: Config


class ComputeRequest(_CamelModel):
  session_id: str = Field(alias="sessionId")
  dt: float
  temperature: Temperature


class ComputeResponse(_CamelModel):
  state: SimState


class ClickRequest(_CamelModel):
  session_id: str = Field(alias="sessionId")
  x: float
  y: float


class ClickResponse(_CamelModel):
  ack: Literal[True] = True


# In-memory session store. Holds the *internal* ParticleState (the
# dataclass returned by setup / go), not the wire shape — heading and
# speed are kept here so /compute can advance the simulation but never
# appear on the wire.
SESSIONS: dict[str, Any] = {}


def _get_vault_state():
  """Return forge-moda's loaded registry/resolver from the server's vault
  session manager. Imported lazily because server.py imports this module
  for the router; doing it at import time would cycle.
  """
  from forge.api.server import _manager  # noqa: WPS433 — see docstring
  _manager.connect(FORGE_MODA_VAULT_PATH)
  return _manager.get(FORGE_MODA_VAULT_PATH)


def _run_snippet(snippet_id: str, args=(), inputs=None):
  """Resolve and execute one snippet from the forge-moda vault.

  Mirrors the action-snippet branch of server.py's /compute. Returns the
  raw Python result (whatever the snippet's compute(...) returned), not
  the serialized wire shape.
  """
  inputs = inputs or {}
  state = _get_vault_state()
  if state is None:
    raise HTTPException(status_code=500, detail="forge-moda vault failed to load")
  try:
    snippet = state["resolver"].resolve(snippet_id)
  except SnippetResolutionError as e:
    raise HTTPException(status_code=500, detail=f"snippet {snippet_id!r} not found in forge-moda: {e}")

  snippet_type = snippet["meta"].get("type")
  if snippet_type in ("data", "snapshot"):
    return read_data_snippet(snippet)

  if snippet_type != "action":
    raise HTTPException(status_code=500, detail=f"snippet {snippet_id!r} has unexpected type: {snippet_type}")

  code = extract_python(snippet["body"])
  if code is None:
    raise HTTPException(status_code=500, detail=f"snippet {snippet_id!r} has no Python facet")

  try:
    _, result = exec_python(
      code, inputs, state["resolver"],
      args=args,
      vault_path=FORGE_MODA_VAULT_PATH,
      registry=state["registry"],
      # Use the resolver's qualified id (e.g. "authoring/setup") rather
      # than the bare input — captured edges land under that namespace,
      # which is also what the plugin's edges panel queries by.
      snippet_id=snippet["snippet_id"],
    )
  except SnippetExecError as e:
    raise HTTPException(status_code=500, detail=f"snippet {snippet_id!r} execution failed: {e}")
  return result


def _serialize_particles(particle_state) -> list[Particle]:
  """Materialize one wire-shape Particle per row of `particle_state`'s arrays.

  Phase 7: ParticleState now stores per-particle fields as parallel numpy
  arrays rather than a list[Particle]. This is the single place we cross
  the array → per-row-dataclass boundary on the server — the rest of the
  per-tick pipeline never iterates particles. `heading` and `speed`
  remain internal-only and are intentionally absent from the wire view.
  """
  ids = particle_state.ids
  types = particle_state.types
  xs = particle_state.xs
  ys = particle_state.ys
  masses = particle_state.masses
  return [
    Particle(
      id=int(ids[i]),
      type=str(types[i]),
      x=float(xs[i]),
      y=float(ys[i]),
      mass=str(masses[i]),
    )
    for i in range(int(ids.shape[0]))
  ]


router = APIRouter(prefix="/moda")


KNOWN_SCENARIOS: frozenset[str] = frozenset({"default_diffusion", "hot_chamber_start"})


@router.post("/init")
def init(req: InitRequest) -> dict:
  # Phase 6: scenarioId is threaded through to setup, which reads the
  # named data snippet (water_count / ink_count / width / height /
  # temperature) and assembles the initial ParticleState. Validate
  # against the known set so a typo returns 400 instead of dying in
  # snippet resolution.
  if req.scenario_id not in KNOWN_SCENARIOS:
    raise HTTPException(
      status_code=400,
      detail=(
        f"unknown scenarioId: {req.scenario_id!r}; "
        f"known: {sorted(KNOWN_SCENARIOS)}"
      ),
    )

  particle_state = _run_snippet("setup", args=(req.scenario_id,))
  session_id = uuid4().hex
  SESSIONS[session_id] = particle_state

  response = InitResponse(
    session_id=session_id,
    state=SimState(
      tick=particle_state.tick,
      particles=_serialize_particles(particle_state),
    ),
    config=Config(
      width=int(particle_state.width),
      height=int(particle_state.height),
      temperature_levels=["zero", "low", "medium", "high"],
    ),
  )
  return response.model_dump(by_alias=True)


@router.post("/compute")
def compute(req: ComputeRequest) -> dict:
  particle_state = SESSIONS.get(req.session_id)
  if particle_state is None:
    raise HTTPException(status_code=404, detail=f"unknown sessionId: {req.session_id!r}")

  # Phase 6: temperature now actually does something. `go` reads it on
  # entry and feeds it to set_water_speed_from_temperature before the
  # rest of the per-tick pipeline. `dt` and `state` flow in unchanged.
  start = time.perf_counter()
  new_state = _run_snippet("go", args=(particle_state, req.dt, req.temperature))
  elapsed_ms = (time.perf_counter() - start) * 1000
  logger.info("moda /compute: elapsed_ms=%.1f", elapsed_ms)

  SESSIONS[req.session_id] = new_state
  return ComputeResponse(
    state=SimState(
      tick=new_state.tick,
      particles=_serialize_particles(new_state),
    ),
  ).model_dump(by_alias=True)


@router.post("/click")
def click(req: ClickRequest) -> dict:
  particle_state = SESSIONS.get(req.session_id)
  if particle_state is None:
    raise HTTPException(status_code=404, detail=f"unknown sessionId: {req.session_id!r}")

  # Phase 4: drop ink particles at the click position via the on_click
  # root snippet. The wire response stays {ack: true}; the new state
  # surfaces on the next /compute by the Phase 0 design decision.
  start = time.perf_counter()
  new_state = _run_snippet("on_click", args=(particle_state, req.x, req.y))
  elapsed_ms = (time.perf_counter() - start) * 1000
  logger.info("moda /click: elapsed_ms=%.1f", elapsed_ms)

  SESSIONS[req.session_id] = new_state
  return ClickResponse().model_dump(by_alias=True)
