"""Moda-domain prompt fragment for /generate.

Importing this module registers a fragment that augments the base
system prompt with the conventions moda snippets follow:
- ParticleState stores per-particle fields as parallel numpy arrays
  (Phase 7 tech-debt refactor); generated code reads and writes
  those arrays directly with no per-particle Python iteration
- the Particle dataclass remains as the wire-view schema (the
  /moda/compute serializer materializes one Particle per row at the
  HTTP boundary), but snippets DO NOT construct Particle objects
  inside the per-tick pipeline
- ParticleState and Particle are pre-injected as globals; generated
  code uses them by name without writing `from ... import ...`
"""

from forge.core.llm_prompts import register_fragment


MODA_PROMPT_FRAGMENT = """Moda-domain types already bound as globals (do NOT write
`from forge_moda_core import ...` — the runtime forbids imports):
  Particle, ParticleState

ParticleState fields (struct-of-arrays — every per-particle field is a
parallel numpy array of length N; the same index across arrays
identifies one particle):
  tick     (int)             — simulation tick counter
  ids      (numpy.ndarray)   — (N,) int64,   per-particle stable id
  types    (numpy.ndarray)   — (N,) object,  'water' | 'ink'
  xs       (numpy.ndarray)   — (N,) float64, x position
  ys       (numpy.ndarray)   — (N,) float64, y position
  headings (numpy.ndarray)   — (N,) float64, radians in [0, 2π)
  speeds   (numpy.ndarray)   — (N,) float64, units per second
  masses   (numpy.ndarray)   — (N,) object,  'light' | 'medium' | 'heavy'
  width    (float)           — chamber width
  height   (float)           — chamber height

Particle is a wire-view dataclass with fields
  id (int), type, x (float), y (float), heading (float),
  speed (float), mass.
It exists ONLY for the /moda/compute serializer (one Particle per row
at the HTTP boundary) and for documentation. Snippets MUST NOT iterate
over a list of Particle in the per-tick pipeline — operate on the
arrays directly.

Composition rules
- When transforming an existing state, copy unchanged arrays through
  by reference (assignment, not numpy.array(...) copy) and produce
  fresh arrays only for fields you change. Cheap and explicit.
- To filter a subset (e.g., water-only), build a boolean mask
  (`is_water = state.types == 'water'`) and index into the relevant
  array with the mask. No `for p in ...` loops.
- To append new rows (e.g., create_ink_particles_at_position adds N
  ink particles to an existing state), use numpy.concatenate on each
  field array. Generate new ids as `numpy.arange(max_id + 1,
  max_id + 1 + count)`; new types/masses as
  `numpy.full(count, 'ink', dtype=object)` etc.
- To build a fresh state from scratch (create_water_particles), build
  the per-field arrays in one vectorized pass:
    ids = numpy.arange(count)
    xs = numpy.random.uniform(0, width, count)
    ...
    types = numpy.full(count, 'water', dtype=object)
  Then return ParticleState(tick=tick, ids=ids, types=types, xs=xs,
                            ys=ys, headings=headings, speeds=speeds,
                            masses=masses, width=width, height=height).
- ParticleState's `tick` always advances inside move_all_particles
  (or whichever leaf increments time); every other leaf carries
  `state.tick` through unchanged.

Hard rules
- NO Python `for` loops over particles. Use numpy broadcasting and
  fancy indexing. Even at N=200 the vectorization discipline avoids
  the per-tick overhead that drove Phase 6's perf tail.
- NO list comprehensions that materialize Particle objects inside a
  leaf. Particle is wire-only.
- NO `state.particles` — that field is gone. The arrays are the
  source of truth."""


register_fragment(MODA_PROMPT_FRAGMENT)
