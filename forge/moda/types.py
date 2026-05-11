"""Shared dataclasses for moda-domain snippets.

`Particle` and `ParticleState` are pre-injected into the snippet
namespace by the executor (alongside numpy and the music21 names) so
generated code can build them by name without writing `import`
statements — the base /generate prompt forbids those.

Wire serialization drops `heading` and `speed`; those are internal
fields used by the simulation but never sent to the client.
"""

from dataclasses import dataclass, field
from typing import Literal


ParticleType = Literal["water", "ink"]
ParticleMass = Literal["light", "medium", "heavy"]


@dataclass
class Particle:
  id: int
  type: ParticleType
  x: float
  y: float
  heading: float
  speed: float
  mass: ParticleMass


@dataclass
class ParticleState:
  tick: int
  particles: list
  width: float
  height: float
