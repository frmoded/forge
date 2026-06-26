"""High-level moda chips for V2 E-- snippets (per v2-spec §17).

V1 forge-moda content was numpy-heavy: each `compute()` open-coded
boolean masks, array constructors, broadcast math, and ParticleState
re-construction. V2 cohort surface targets a tiny dialect — Let/Call/
Return/If/Otherwise + arithmetic — so the numpy work has to move into
engine chips that snippets *call* by wikilink.

Each chip below:
- Takes the inputs cohort authors will pass via `Call [[name]] with k=v`.
- Returns the appropriate ParticleState (or scalar / dict / None).
- Stays a pure function except `show_simulation`, which is the plugin
  render hook (spec §1.6 side effect; engine returns state, plugin
  picks up the value-shaped result for the iframe).
- Carries a docstring usable as a chip-palette tooltip.

The chips wrap the same numpy idioms the V1 snippets used; semantic
equivalence is locked in by `tests/moda/test_lib_v2_chips.py`. When a
chip and a V1 snippet diverge during the migration, the chip is the
canonical V2 surface and the V1 snippet body becomes a thin
context.compute shim until the note is migrated.

Why a separate lib (parallel to `forge.music.lib`): keeping numpy out
of vault content lets `forge.recipe.transpile` emit a
chip-call expression without leaking implementation. Cohort sees
`Call [[advance_positions]] with state=state, dt=0.0333.` instead of
`state.xs + state.speeds * numpy.cos(state.headings) * dt`.
"""

import math
import random
import string

import numpy

from forge.moda.types import ParticleState


# ---------------------------------------------------------------------------
# §17.1 — temperature → speed mapping
# ---------------------------------------------------------------------------

_TEMPERATURE_SPEEDS = {
    "zero": 0.0,
    "low": 20.0,
    "medium": 50.0,
    "high": 100.0,
}


def temperature_to_speed(temperature):
    """Map a temperature label ("zero" | "low" | "medium" | "high") to a
    numeric speed constant. Unknown labels fall back to medium (50.0)
    so the simulation keeps moving rather than freezing — matching the
    V1 `speed_for_temperature.md` behavior exactly."""
    return float(_TEMPERATURE_SPEEDS.get(temperature, 50.0))


# ---------------------------------------------------------------------------
# §17.2 — chamber + particle factories
# ---------------------------------------------------------------------------

def create_chamber(width=800.0, height=600.0):
    """Build an empty ParticleState scaffolding for a chamber of the given
    dimensions. No particles; tick = 0. Use as the starting point for
    `setup`-style compositions that then append water/ink populations."""
    return ParticleState(
        tick=0,
        ids=numpy.array([], dtype=numpy.int64),
        types=numpy.array([], dtype=object),
        xs=numpy.array([], dtype=numpy.float64),
        ys=numpy.array([], dtype=numpy.float64),
        headings=numpy.array([], dtype=numpy.float64),
        speeds=numpy.array([], dtype=numpy.float64),
        masses=numpy.array([], dtype=object),
        width=float(width),
        height=float(height),
    )


def _next_id(state, count):
    """Return a fresh id range of length `count` that picks up just past
    state's current maximum id (or starts at 0 if state is empty)."""
    if len(state.ids) == 0:
        max_id = -1
    else:
        max_id = int(state.ids.max())
    return numpy.arange(max_id + 1, max_id + 1 + count)


def _append_particles(state, *, new_ids, new_types, new_xs, new_ys,
                     new_headings, new_speeds, new_masses):
    """Concatenate fresh particle arrays onto state's per-field arrays
    and rebuild ParticleState. Shared helper for water/ink factories."""
    return ParticleState(
        tick=state.tick,
        ids=numpy.concatenate([state.ids, new_ids]),
        types=numpy.concatenate([state.types, new_types]),
        xs=numpy.concatenate([state.xs, new_xs]),
        ys=numpy.concatenate([state.ys, new_ys]),
        headings=numpy.concatenate([state.headings, new_headings]),
        speeds=numpy.concatenate([state.speeds, new_speeds]),
        masses=numpy.concatenate([state.masses, new_masses]),
        width=state.width,
        height=state.height,
    )


def create_water_particles(state, count=500):
    """Append `count` water particles to state with uniformly random
    positions across the full chamber, random initial headings, zero
    initial speed, and a 'medium' mass placeholder. Cohort calls this
    inside `setup` to populate the chamber, then sets speed via
    [[set_speed_for_type]] with their chosen temperature."""
    width = state.width
    height = state.height
    new_ids = _next_id(state, count)
    new_types = numpy.full(count, "water", dtype=object)
    new_xs = numpy.random.uniform(0, width, count)
    new_ys = numpy.random.uniform(0, height, count)
    new_headings = numpy.random.uniform(0, 2 * math.pi, count)
    new_speeds = numpy.zeros(count, dtype=numpy.float64)
    new_masses = numpy.full(count, "medium", dtype=object)
    return _append_particles(
        state,
        new_ids=new_ids, new_types=new_types,
        new_xs=new_xs, new_ys=new_ys,
        new_headings=new_headings, new_speeds=new_speeds,
        new_masses=new_masses,
    )


def create_ink_particles(state, x, y, count=50, radius=5.0):
    """Append `count` ink particles to state as a tight cluster centred
    on (x, y). Positions are uniform within a disk of `radius`
    (sqrt-trick for area-density uniformity); headings randomized; zero
    initial speed; 'medium' mass placeholder. Fired by the click
    handler (`on_mouse_click`)."""
    new_ids = _next_id(state, count)
    new_types = numpy.full(count, "ink", dtype=object)
    # Uniform-in-disk: r = sqrt(u) * R gives uniform area density.
    r = numpy.sqrt(numpy.random.uniform(0, 1, count)) * radius
    theta = numpy.random.uniform(0, 2 * math.pi, count)
    new_xs = float(x) + r * numpy.cos(theta)
    new_ys = float(y) + r * numpy.sin(theta)
    new_headings = numpy.random.uniform(0, 2 * math.pi, count)
    new_speeds = numpy.zeros(count, dtype=numpy.float64)
    new_masses = numpy.full(count, "medium", dtype=object)
    return _append_particles(
        state,
        new_ids=new_ids, new_types=new_types,
        new_xs=new_xs, new_ys=new_ys,
        new_headings=new_headings, new_speeds=new_speeds,
        new_masses=new_masses,
    )


# ---------------------------------------------------------------------------
# §17.3 — kinematics + collisions
# ---------------------------------------------------------------------------

def advance_positions(state, dt):
    """Move every particle one tick forward via
    `x += speed * cos(heading) * dt` and `y += speed * sin(heading) * dt`
    (vectorized). Bumps tick by 1. All other fields preserved.
    This is the kinematic core of `[[move]]`."""
    new_xs = state.xs + state.speeds * numpy.cos(state.headings) * dt
    new_ys = state.ys + state.speeds * numpy.sin(state.headings) * dt
    return ParticleState(
        tick=state.tick + 1,
        ids=state.ids,
        types=state.types,
        xs=new_xs,
        ys=new_ys,
        headings=state.headings,
        speeds=state.speeds,
        masses=state.masses,
        width=state.width,
        height=state.height,
    )


def bounce_off_walls(state):
    """Reflect particles that have crossed a chamber bound:
    vertical walls flip heading via `π - heading`; horizontal walls
    flip via `-heading`; the resulting heading is normalized modulo
    `2π`. Position is clamped back inside the bounds so the next
    `advance_positions` tick stays in-chamber. Particles inside the
    chamber are unchanged."""
    xs = state.xs.copy()
    ys = state.ys.copy()
    headings = state.headings.copy()

    hits_left = xs < 0
    hits_right = xs > state.width
    hits_bottom = ys < 0
    hits_top = ys > state.height

    hits_vertical = hits_left | hits_right
    hits_horizontal = hits_bottom | hits_top

    headings[hits_vertical] = math.pi - headings[hits_vertical]
    headings[hits_horizontal] = -headings[hits_horizontal]
    headings = headings % (2 * math.pi)

    xs[hits_left] = 0.0
    xs[hits_right] = state.width
    ys[hits_bottom] = 0.0
    ys[hits_top] = state.height

    return ParticleState(
        tick=state.tick,
        ids=state.ids,
        types=state.types,
        xs=xs,
        ys=ys,
        headings=headings,
        speeds=state.speeds,
        masses=state.masses,
        width=state.width,
        height=state.height,
    )


def detect_collisions(state, radius=5.0):
    """Find every colliding pair this tick and return an (M, 2) int64
    array of (i, j) row indices. Two particles collide when they are
    within `radius` units AND their separation is shrinking
    (`(p_j - p_i) · (v_j - v_i) < 0`). The shrinking-separation filter
    prevents just-swapped pairs from re-colliding next tick (empirically
    85.7% → 3.5% recurrence with the filter, per V1 `interact.md`'s
    generation notes). If state has < 2 particles, returns an empty
    (0, 2) array."""
    N = len(state.xs)
    empty = numpy.empty((0, 2), dtype=numpy.int64)
    if N < 2:
        return empty
    vx = state.speeds * numpy.cos(state.headings)
    vy = state.speeds * numpy.sin(state.headings)
    ii, jj = numpy.triu_indices(N, k=1)
    dx = state.xs[jj] - state.xs[ii]
    dy = state.ys[jj] - state.ys[ii]
    dist_sq = dx * dx + dy * dy
    dvx = vx[jj] - vx[ii]
    dvy = vy[jj] - vy[ii]
    approach = dx * dvx + dy * dvy
    collision_mask = (dist_sq <= radius * radius) & (approach < 0.0)
    if not numpy.any(collision_mask):
        return empty
    return numpy.column_stack((ii[collision_mask], jj[collision_mask]))


def bounce_off_pairs(state, pairs):
    """For every (i, j) row in `pairs` (an (M, 2) int64 array, typically
    produced by [[detect_collisions]]), swap headings[i] ↔ headings[j].
    All other fields preserved. If `pairs` is empty, returns state
    unchanged. This is a heading-swap approximation of an elastic
    collision — same simplification V1 used."""
    if pairs is None:
        return state
    pairs_arr = numpy.asarray(pairs)
    if pairs_arr.size == 0:
        return state
    headings = state.headings.copy()
    i_indices = pairs_arr[:, 0]
    j_indices = pairs_arr[:, 1]
    headings[i_indices] = state.headings[j_indices]
    headings[j_indices] = state.headings[i_indices]
    return ParticleState(
        tick=state.tick,
        ids=state.ids,
        types=state.types,
        xs=state.xs,
        ys=state.ys,
        headings=headings,
        speeds=state.speeds,
        masses=state.masses,
        width=state.width,
        height=state.height,
    )


# ---------------------------------------------------------------------------
# §17.4 — typed field setters (speed + mass)
# ---------------------------------------------------------------------------

def set_speed_for_type(state, particle_type, speed):
    """Set `speeds[where types == particle_type]` to the given numeric
    `speed`. Other particle types untouched. Replaces the V1
    set_{water,ink}_speed + set_speed_{high,low,medium,zero} family
    (cohort threads the temperature label through
    [[temperature_to_speed]] first)."""
    is_match = state.types == particle_type
    speeds = state.speeds.copy()
    speeds[is_match] = float(speed)
    return ParticleState(
        tick=state.tick,
        ids=state.ids,
        types=state.types,
        xs=state.xs,
        ys=state.ys,
        headings=state.headings,
        speeds=speeds,
        masses=state.masses,
        width=state.width,
        height=state.height,
    )


def set_mass_for_type(state, particle_type, mass):
    """Set `masses[where types == particle_type]` to the given mass label
    ("light" | "medium" | "heavy"). Other particle types untouched.
    Replaces V1 set_{water,ink}_mass."""
    is_match = state.types == particle_type
    masses = state.masses.copy()
    masses[is_match] = mass
    return ParticleState(
        tick=state.tick,
        ids=state.ids,
        types=state.types,
        xs=state.xs,
        ys=state.ys,
        headings=state.headings,
        speeds=state.speeds,
        masses=masses,
        width=state.width,
        height=state.height,
    )


# ---------------------------------------------------------------------------
# §17.5 — simulation orchestration helpers
# ---------------------------------------------------------------------------

def group_clicks_by_tick(clicks):
    """Convert a `sample_clicks`-shaped list of click events
    [{"tick": int, "x": float, "y": float}, ...] into a dict
    {tick: [(x, y), ...]}. Lets `simulation.md` dispatch clicks via a
    cheap dict lookup inside its per-tick loop instead of re-scanning
    the full clicks list each tick."""
    by_tick = {}
    for ev in clicks:
        by_tick.setdefault(ev["tick"], []).append((ev["x"], ev["y"]))
    return by_tick


def apply_clicks_at_tick(state, clicks_by_tick, tick, on_click=None):
    """Resolve any clicks scheduled for `tick` (from a dict produced by
    [[group_clicks_by_tick]]) and fold them into state by calling
    `on_click(state, x, y)` once per event. `on_click` defaults to
    [[create_ink_particles]] — the canonical click outcome in V1
    on_mouse_click — so the simplest moda compositions don't need to
    pass it explicitly. Returns the post-fold state. If no clicks for
    this tick, returns state unchanged."""
    if on_click is None:
        on_click = lambda s, x, y: create_ink_particles(s, x, y)
    events = clicks_by_tick.get(tick, [])
    for x, y in events:
        state = on_click(state, x, y)
    return state


# ---------------------------------------------------------------------------
# §17.6 — name + render utilities
# ---------------------------------------------------------------------------

def random_name(n=5):
    """Generate a random N-character lowercase ASCII name. Used by the
    canonical-form demos (slot_demo, canonical_demo_compose). Default
    `n=5` matches V1's canonical_demo_compose call shape."""
    return "".join(random.choices(string.ascii_lowercase, k=int(n)))


def tick_range(n):
    """Return `[0, 1, ..., n-1]` as a plain Python list. Workaround for
    V2 parser's missing `range(N)` support — used as the iterable in
    `For each tick in Call [[tick_range]] with n=300:` constructions.

    Returning a list (not a range) keeps the For-each transpiler happy
    and keeps the iteration eager-evaluated; simulation.md's 300-tick
    loop is trivially small."""
    return list(range(int(n)))


def show_simulation(state):
    """Render the simulation iframe with the given final ParticleState.

    Engine-side: this is a passthrough that returns the state (so a V2
    composition `Return Call [[show_simulation]] with state=final_state.`
    still produces the final state as its return value).

    Plugin-side: the renderer recognises the call as a render chip
    (parallel to `show_score` for music) and opens the moda iframe with
    the returned ParticleState as its initial frame. The plugin-side
    hook is wired in the follow-up drain that migrates `simulation.md`
    to V2; until then this chip is a no-op renderer (engine smoke
    passes; iframe opens via the existing V1 path).

    Per spec §1.6: side-effecting chips return a value-shaped result so
    they compose cleanly with `Return Call [[name]] with ...`."""
    return state
