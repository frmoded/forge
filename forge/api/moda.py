"""Phase 0 of the forge-moda integration: protocol round-trip only.

This router exposes /init, /compute, /click under the /moda prefix and is
purely a stub — no Forge engine, no snippets, no LLM. The endpoints return
hardcoded data so the client can prove the iframe ↔ HTTP loop works end
to end before any real simulation logic lands.

Wire format is camelCase JSON; Pydantic uses snake_case attributes with
aliases so the rest of the Python code reads idiomatic.
"""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field


Temperature = Literal["zero", "low", "medium", "high"]
ParticleType = Literal["water", "ink"]
ParticleMass = Literal["light", "medium", "heavy"]


class _CamelModel(BaseModel):
  # Accept both alias (camelCase, on the wire) and field name (snake_case,
  # in Python). by_alias=True is set when serializing responses below.
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


# In-memory session store. Phase 0 only — no persistence, no eviction.
SESSIONS: dict[str, SimState] = {}


def _seed_state() -> SimState:
  particles = [
    Particle(id=i, type="water", x=100.0 * (i + 1), y=100.0 * (i + 1), mass="medium")
    for i in range(5)
  ]
  return SimState(tick=0, particles=particles)


router = APIRouter(prefix="/moda")


@router.post("/init")
def init(req: InitRequest) -> dict:
  # scenario_id is accepted but ignored for Phase 0 — the seed state is the
  # same regardless. Phase 1+ will look it up against forge-moda scenarios.
  _ = req.scenario_id
  session_id = uuid4().hex
  state = _seed_state()
  SESSIONS[session_id] = state
  response = InitResponse(
    session_id=session_id,
    state=state,
    config=Config(width=800, height=600, temperature_levels=["zero", "low", "medium", "high"]),
  )
  return response.model_dump(by_alias=True)


@router.post("/compute")
def compute(req: ComputeRequest) -> dict:
  state = SESSIONS.get(req.session_id)
  if state is None:
    raise HTTPException(status_code=404, detail=f"unknown sessionId: {req.session_id!r}")
  # Phase 0: no advancement. dt and temperature are accepted but ignored.
  return ComputeResponse(state=state).model_dump(by_alias=True)


@router.post("/click")
def click(req: ClickRequest) -> dict:
  if req.session_id not in SESSIONS:
    raise HTTPException(status_code=404, detail=f"unknown sessionId: {req.session_id!r}")
  # Phase 0: coords are accepted but ignored.
  _ = (req.x, req.y)
  return ClickResponse().model_dump(by_alias=True)
