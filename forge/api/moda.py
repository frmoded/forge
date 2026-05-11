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

import os
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from forge.core.executor import extract_python, exec_python, SnippetExecError, read_data_snippet
from forge.core.exceptions import SnippetResolutionError


# Authoritative vault for the simulator. The override exists so this
# isn't pinned to one developer's machine, but the default is the
# expected layout — Forge's plan documents put forge-moda alongside
# forge in ~/projects/.
FORGE_MODA_VAULT_PATH = os.environ.get(
  "FORGE_MODA_VAULT_PATH",
  os.path.expanduser("~/projects/forge-moda"),
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
      snippet_id=snippet_id,
    )
  except SnippetExecError as e:
    raise HTTPException(status_code=500, detail=f"snippet {snippet_id!r} execution failed: {e}")
  return result


def _serialize_particles(particles) -> list[Particle]:
  """Drop internal `heading` and `speed` to produce the wire shape."""
  return [
    Particle(id=p.id, type=p.type, x=p.x, y=p.y, mass=p.mass)
    for p in particles
  ]


router = APIRouter(prefix="/moda")


@router.post("/init")
def init(req: InitRequest) -> dict:
  # scenarioId is accepted but ignored in Phase 1 — `setup` is hardcoded
  # to default_diffusion via the snippet graph. Phase 3+ will look up
  # the scenario by id.
  _ = req.scenario_id

  particle_state = _run_snippet("setup")
  session_id = uuid4().hex
  SESSIONS[session_id] = particle_state

  response = InitResponse(
    session_id=session_id,
    state=SimState(
      tick=particle_state.tick,
      particles=_serialize_particles(particle_state.particles),
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
  # Phase 1: no advancement. Phase 2 will invoke `go(state, dt)` here.
  return ComputeResponse(
    state=SimState(
      tick=particle_state.tick,
      particles=_serialize_particles(particle_state.particles),
    ),
  ).model_dump(by_alias=True)


@router.post("/click")
def click(req: ClickRequest) -> dict:
  if req.session_id not in SESSIONS:
    raise HTTPException(status_code=404, detail=f"unknown sessionId: {req.session_id!r}")
  _ = (req.x, req.y)
  return ClickResponse().model_dump(by_alias=True)
