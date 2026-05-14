# Tech debt

## Per-vault Python dependencies

Today, third-party Python libraries that vaults need are installed globally
in the Forge backend's environment. The `forge-music` vault depends on
`music21`, so `music21` is currently listed alongside FastAPI and the rest
of Forge's runtime deps in `pyproject.toml`.

This means every Forge install pays the cost of `music21` even if the user
never installs `forge-music`. The cost today is small — `music21` is pure
Python, no native compilation — but the principle is wrong. A backend
shouldn't pre-install every library every published vault might ever need.

The principled solution is **per-vault Python dependency isolation**: each
vault's `forge.toml` declares its Python deps; install provisions a
per-vault virtualenv (or PEP 723-style inline metadata, or another
isolation primitive); the snippet runtime routes a vault's snippets to its
dedicated environment.

### Why we're not doing it now

- **Music is the only confirmed near-term consumer** of third-party Python
  libs. One data point isn't enough to design the boundary against.
- **`music21` is small and pure-Python** — no native deps, no compile
  step, ~30 MB on disk. Adding it globally has minimal footprint cost.
- **Designing the isolation primitive prematurely is expensive**: the
  install-time provisioning logic, the runtime dispatch, and the
  user-facing UX (deps in `forge.toml`, lockfiles?, upgrade flow?) all
  need decisions, and we don't yet have lived experience to know which
  choices matter.
- **The pain we'd be solving for hasn't surfaced.** No vault's deps
  conflict with another's; the global install hasn't gotten heavy enough
  to bother users.

### When to revisit

- A second vault wants a third-party Python lib whose version range
  conflicts with an existing one.
- The backend install footprint exceeds a threshold that bothers users
  (rough order of magnitude: ~200 MB).
- A proposed vault needs a library with native deps (`numpy`, `scipy`,
  `pandas`-with-extras) that meaningfully increases install size or
  install-time risk for users who don't need that vault.

Until one of those, deps stay in `pyproject.toml`. New per-vault deps
need review before merging — the bar is "would this be acceptable as a
permanent backend dep?", not "this vault needs it."

## ParticleState representation — list[dataclass] vs. numpy arrays

**Resolved in Phase 7.** `ParticleState` now stores per-particle fields
as parallel numpy arrays (`ids`, `types`, `xs`, `ys`, `headings`,
`speeds`, `masses`) and the `Particle` dataclass is materialized
row-by-row only at the /moda/compute wire boundary. The seven affected
leaves were regenerated against an updated moda prompt fragment; all
of them operate on the arrays directly with no stack/unstack pass.
The refactor depended on the wire codec gaining `numpy.ndarray`
support, which landed in the commit immediately before this one.

Perf at the previously-tight N=900 dropped avg from 33.3 ms to 19.0 ms
(p95 47.1 → 19.6, over-budget frames 15.7% → 0.7%). The history below
is preserved for the design context it captured.

---

As of Phase 3 (forge-moda), `ParticleState.particles` was a `list[Particle]`
where each `Particle` is a dataclass. Every leaf snippet that does
vectorized math repeats the same dance:

1. Stack particle fields into numpy arrays (one list comprehension per
   field — `xs`, `ys`, `headings`, `speeds`, ...).
2. Do the vectorized math.
3. Unstack: rebuild `list[Particle]` via a list comprehension over
   `zip(...)`.

This pattern now lives in `create_water_particles`, `move_all_particles`,
and `bounce_all_particles_off_walls`. By Phase 5 (collisions) it will
also live in `detect_particle_collisions`,
`resolve_particle_collisions`, and `set_water_speed_from_temperature` —
six leaves repeating the same boilerplate, all of it pure overhead.

At 500 particles the overhead is invisible (~1-2 ms per leaf). At
5,000+ particles the list-comp materialization dominates wall time and
the actual math becomes a minority of per-tick cost.

The principled fix: **store fields as numpy arrays inside
`ParticleState`** (so `ParticleState.xs`, `ParticleState.ys`,
`ParticleState.headings`, etc., each shape `(N,)`), and materialize
`Particle` objects only at the wire-serialization boundary in
`/moda/compute`. Leaves operate directly on the arrays; no stack/unstack
per call.

### Why we're not doing it now

- **Performance budget is comfortable** at 500 particles. Backend
  perf is 4-14 ms per `/compute`, well under the 33 ms target. The
  refactor doesn't unlock any user-visible improvement yet.
- **The repetition isn't unmanageable** — six leaves with the same
  shape is annoying but reviewable. The pattern is consistent enough
  that a future refactor can pattern-match across them.
- **Conference target dominates**. Phase 5 (collisions) is the
  remaining technical unknown; refactoring the storage shape and
  Phase 5 in the same week increases blast radius.

### When to revisit

- Phase 5's measurement comes in *and* the budget is uncomfortable
  (avg backend `/compute` > 25 ms, or p99 > 33 ms sustained). The
  refactor frees ~5-10 ms per tick at 500 particles by eliminating
  the per-leaf materialization passes.
- Particle count crosses ~2,000 (whether via larger scenarios for
  pedagogical purposes or via a stress test). At 2,000 the list-comp
  cost is no longer invisible.
- A new leaf is being authored that would be the seventh consumer of
  the stack/unstack pattern. At that point the boilerplate exceeds
  the cost of just doing the refactor.

Estimated effort: one focused day. Touches `forge/moda/types.py`
(redefine `ParticleState` fields), all leaf snippets (rewrite to
operate on arrays directly — likely simpler than the current code),
and `/moda/compute`'s wire serializer (single materialization step
at the boundary).
