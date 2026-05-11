"""Moda-domain prompt fragment for /generate.

Importing this module registers a fragment that augments the base
system prompt with the conventions moda snippets follow:
- the Particle / ParticleState dataclasses are pre-injected as globals
  (matching how music21 names are exposed) — generated code must use
  them by name without writing `from forge_moda_core import ...`
- vectorized NumPy is the preferred style for per-particle math —
  Phase 5 collisions will need it and we want the discipline now
"""

from forge.core.llm_prompts import register_fragment


MODA_PROMPT_FRAGMENT = """Moda-domain dataclasses already bound as globals (do NOT write
`from forge_moda_core import ...` — the runtime forbids imports):
  Particle, ParticleState

Particle fields:
  id (int), type ('water' | 'ink'), x (float), y (float),
  heading (float, radians in [0, 2π)), speed (float, units per second),
  mass ('light' | 'medium' | 'heavy').

ParticleState fields:
  tick (int), particles (list[Particle]), width (float), height (float).

When a moda snippet produces or transforms particle state, return a
ParticleState — not a dict. Construct particles directly:
  Particle(id=i, type='water', x=..., y=..., heading=..., speed=...,
           mass='medium')

NumPy discipline: when computing per-particle math (positions, motion,
collision pairs), use vectorized numpy operations on stacked arrays —
not Python `for` loops. Even at a few hundred particles, vectorization
is the discipline to set now; collision detection later needs it.
Construct the final list[Particle] from the resulting arrays at the
end of the computation."""


register_fragment(MODA_PROMPT_FRAGMENT)
