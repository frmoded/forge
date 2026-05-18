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
- the 25-block MoDa Unit-1 refactor: English facets are procedural
  per-particle with implicit (ambient) `state`; generated Python
  still takes/returns `state` explicitly. Scope/control blocks are
  pure dispatch over peer snippets; action/property blocks own their
  numpy masks. See the implicit-state + per-particle-vectorization
  sections of the fragment below.
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

Implicit-state convention (forge-moda Unit-1 block style)
- The English facet is written in procedural per-particle style and
  does NOT declare `state` in its `Inputs:` block. `Inputs:` lists
  only non-ambient parameters (`temperature`, `dt`, `x`, `y`) or says
  `Inputs: None`.
- The generated Python facet ALWAYS takes `state` as the first
  argument after `context` — `def compute(context, state, ...)` —
  followed by exactly the non-ambient inputs the English declares, in
  order. It ALWAYS returns a `ParticleState`.
  EXCEPTION — the `setup` block is the state ORIGIN: it has no
  incoming state, so its signature is `def compute(context,
  temperature)` (no `state` param). Its Python builds a fresh empty
  `ParticleState` (zero-length arrays of the right dtypes, tick=0,
  the chamber's width/height) and threads THAT into its
  create/set calls. Every other block takes `state`.
- A block that threads an internally-computed array to a peer (the
  collision-pair array between `interact` -> `if_particle_then_bounce`
  -> `bounce_off_particle`) declares that array in its `inputs:`
  frontmatter so the generated signature carries it
  (`def compute(context, state, pairs)`), and the caller passes it
  as a kwarg (`context.compute("...", state=state, pairs=pairs)`).
  Never invent a snippet to "fetch" such an array — it is passed in.
  Examples:
    English `Inputs: None`           -> def compute(context, state):
    English `Inputs: temperature`    -> def compute(context, state, temperature):
    English `Inputs: x, y`           -> def compute(context, state, x, y):
    English `Inputs: dt`             -> def compute(context, state, dt):
- "the current particle" / "the other particle" inside an
  `ask`/`interact` scope are NOT Python variables — they are the
  vectorized array population. Translate them to operations on
  `state`'s arrays (optionally masked), never to a scalar loop var.

Per-particle / per-pair English -> vectorized Python
- When an English facet says "For each particle in state: call X
  with ..." (the `ask` scopes — blocks 10, 17 — and `interact` —
  block 12), the Python MUST NOT `for`-loop over the particles. It
  calls X ONCE via `context.compute("X", ...)` passing the whole
  `state`; X's own Python does the batching with numpy masks /
  broadcasting and returns the updated `ParticleState`. Thread the
  returned state through successive calls.
- When an English facet (inside a scope) says "set the current
  particle's <prop> to <value>" or "reflect the current particle's
  heading", the Python derives a boolean mask from THIS block's own
  semantics (e.g. `is_water = state.types == 'water'`), copies the
  affected array, assigns into the masked slots, and returns a new
  ParticleState. The block owns its mask — the scope does not pass
  one in.
- Pairwise blocks (`interact` 12, `if_particle_then_bounce` 15,
  `bounce_off_particle` 16) collapse the O(N^2) work into ONE block:
  `interact` computes the full colliding-pair array once
  (`numpy.triu_indices` + distance mask + approach-direction mask)
  and threads it; `if_particle_then_bounce` / `bounce_off_particle`
  operate on that pair array with fancy indexing. None of the three
  loops in Python; "the other particle" is the second column of the
  pair array, not a scalar.

Worked examples

  # Block 19 — set_speed_high. English (inside the water scope):
  #   Inputs: None
  #   Steps: Set the current water particle's speed to the high speed
  #          constant.
  def compute(context, state):
      high = context.compute("speed_for_temperature", temperature='high')
      is_water = state.types == 'water'
      speeds = state.speeds.copy()
      speeds[is_water] = high
      return ParticleState(
          tick=state.tick, ids=state.ids, types=state.types,
          xs=state.xs, ys=state.ys, headings=state.headings,
          speeds=speeds, masses=state.masses,
          width=state.width, height=state.height)

  # Block 17 — ask_water_particles. English:
  #   Inputs: temperature
  #   Steps: For each water particle in state: call
  #          if_temp_high_set_speed / _medium / _low / _zero with
  #          temperature.
  # No loop: each callee is invoked once with the whole state and
  # threads the state forward. Each if_temp_* block no-ops unless its
  # temperature branch matches, and the set_speed_* it calls applies
  # the water mask itself.
  def compute(context, state, temperature):
      state = context.compute("if_temp_high_set_speed", state=state, temperature=temperature)
      state = context.compute("if_temp_medium_set_speed", state=state, temperature=temperature)
      state = context.compute("if_temp_low_set_speed", state=state, temperature=temperature)
      state = context.compute("if_temp_zero_set_speed", state=state, temperature=temperature)
      return state

Hard rules
- NO Python `for` loops over particles or pairs. Use numpy
  broadcasting and fancy indexing. Even at N=200 the vectorization
  discipline avoids the per-tick overhead that drove Phase 6's tail.
- NO list comprehensions that materialize Particle objects inside a
  leaf. Particle is wire-only.
- NO `state.particles` — that field is gone. The arrays
  (state.xs / ys / types / speeds / headings / masses / ids) are the
  source of truth.
- Scope/control blocks (`ask_*`, `if_*_then_*`, `interact`) are pure
  dispatch: they `context.compute(...)` peer blocks and thread the
  returned `ParticleState`. They contain no per-particle math
  themselves; the action/property blocks they call own the masks and
  the numpy work."""


register_fragment(MODA_PROMPT_FRAGMENT)
