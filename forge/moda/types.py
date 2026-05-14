"""Shared dataclasses for moda-domain snippets.

Phase 7 refactor: ParticleState stores per-particle fields as parallel
numpy arrays (struct-of-arrays) rather than a Python list of Particle
instances. Every moda leaf operates on the arrays directly; the
`Particle` dataclass below stays as the wire-view schema and is
materialized one-row-at-a-time only at the /moda/compute HTTP
boundary. The injected globals (Particle, ParticleState) are both
still bound on the executor so leaves and the API serializer can name
the types directly.

Why arrays-first: the previous shape forced every leaf to stack arrays
from the list, do its vectorized math, and unstack back into a list
of Particle — seven such round-trips per /compute tick. The pure
overhead pushed average tick time over the 33 ms budget at N=900.
With the wire codec now supporting numpy.ndarray (see
docs/specs/wire-format.md), snapshot capture round-trips arrays
directly and the stack/unstack dance disappears.

Wire serialization still drops `heading` and `speed` — those remain
internal simulation fields.
"""

from dataclasses import dataclass
from typing import Literal

import numpy


ParticleType = Literal["water", "ink"]
ParticleMass = Literal["light", "medium", "heavy"]


@dataclass
class Particle:
  """Per-particle wire view — one row of a ParticleState's arrays.

  Materialized by /moda/compute's serializer in a single pass at the
  HTTP boundary, and used by the moda prompt fragment as the schema
  description. NOT constructed inside the per-tick pipeline; leaves
  operate on ParticleState's arrays directly.
  """

  id: int
  type: ParticleType
  x: float
  y: float
  heading: float
  speed: float
  mass: ParticleMass


@dataclass
class ParticleState:
  """Struct-of-arrays simulation state. All per-particle arrays share
  length N; the same index across them identifies one particle.

  Snippet authors: read state.xs / state.ys / state.types / etc.
  directly and construct a new ParticleState with fresh arrays when
  you change something. Don't iterate. Don't materialize Particle
  objects.
  """

  tick: int
  ids: numpy.ndarray       # (N,) int64
  types: numpy.ndarray     # (N,) object — 'water' | 'ink'
  xs: numpy.ndarray        # (N,) float64
  ys: numpy.ndarray        # (N,) float64
  headings: numpy.ndarray  # (N,) float64, radians in [0, 2π)
  speeds: numpy.ndarray    # (N,) float64, sim units per second
  masses: numpy.ndarray    # (N,) object — 'light' | 'medium' | 'heavy'
  width: float
  height: float
