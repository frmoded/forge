"""Pytest for forge.moda.lib — the V2 moda chip library.

Each chip gets a focused test: shape preservation, semantic
equivalence vs the V1 numpy idiom it wraps, and edge cases (empty
state, zero pairs, unknown labels).

These tests are pure-Python; no vault required. They lock in the
contract V2 cohort snippets rely on.
"""

import math

import numpy
import pytest

from forge.moda import lib
from forge.moda.types import ParticleState
from tests.moda._helpers import make_state


# ---------------------------------------------------------------------------
# temperature_to_speed
# ---------------------------------------------------------------------------

def test_temperature_to_speed_known_labels():
    assert lib.temperature_to_speed("zero") == 0.0
    assert lib.temperature_to_speed("low") == 20.0
    assert lib.temperature_to_speed("medium") == 50.0
    assert lib.temperature_to_speed("high") == 100.0


def test_temperature_to_speed_unknown_falls_back_to_medium():
    # V1 speed_for_temperature.md: mapping.get(temperature, 50.0).
    assert lib.temperature_to_speed("blistering") == 50.0
    assert lib.temperature_to_speed(None) == 50.0


def test_temperature_to_speed_returns_float():
    # Cohort treats this as a numeric — must be float, not int.
    assert isinstance(lib.temperature_to_speed("zero"), float)
    assert isinstance(lib.temperature_to_speed("high"), float)


# ---------------------------------------------------------------------------
# create_chamber
# ---------------------------------------------------------------------------

def test_create_chamber_default_dimensions():
    state = lib.create_chamber()
    assert state.width == 800.0
    assert state.height == 600.0
    assert state.tick == 0
    assert len(state.ids) == 0
    assert len(state.xs) == 0
    assert len(state.masses) == 0


def test_create_chamber_custom_dimensions():
    state = lib.create_chamber(width=1024, height=512)
    assert state.width == 1024.0
    assert state.height == 512.0


def test_create_chamber_array_dtypes():
    # Downstream chips assume these dtypes when concatenating new
    # particles in. Lock them in here.
    state = lib.create_chamber()
    assert state.ids.dtype == numpy.int64
    assert state.xs.dtype == numpy.float64
    assert state.ys.dtype == numpy.float64
    assert state.speeds.dtype == numpy.float64
    assert state.headings.dtype == numpy.float64


# ---------------------------------------------------------------------------
# create_water_particles
# ---------------------------------------------------------------------------

def test_create_water_particles_count_and_types():
    state = lib.create_chamber()
    state = lib.create_water_particles(state, count=10)
    assert len(state.ids) == 10
    assert (state.types == "water").all()
    assert (state.masses == "medium").all()
    assert (state.speeds == 0.0).all()


def test_create_water_particles_ids_continue_from_max():
    state = lib.create_chamber()
    state = lib.create_water_particles(state, count=3)
    state = lib.create_water_particles(state, count=2)
    assert list(state.ids) == [0, 1, 2, 3, 4]


def test_create_water_particles_positions_within_chamber():
    state = lib.create_chamber(width=200, height=150)
    state = lib.create_water_particles(state, count=100)
    assert (state.xs >= 0).all() and (state.xs <= 200).all()
    assert (state.ys >= 0).all() and (state.ys <= 150).all()


# ---------------------------------------------------------------------------
# create_ink_particles
# ---------------------------------------------------------------------------

def test_create_ink_particles_clustered_at_point():
    state = lib.create_chamber(width=800, height=600)
    state = lib.create_water_particles(state, count=5)
    state = lib.create_ink_particles(state, x=400.0, y=300.0,
                                     count=50, radius=5.0)
    ink_mask = state.types == "ink"
    ink_xs = state.xs[ink_mask]
    ink_ys = state.ys[ink_mask]
    # All ink particles within radius of click.
    dists = numpy.sqrt((ink_xs - 400.0) ** 2 + (ink_ys - 300.0) ** 2)
    assert (dists <= 5.0 + 1e-9).all()


def test_create_ink_particles_ids_unique_across_water_and_ink():
    state = lib.create_chamber()
    state = lib.create_water_particles(state, count=5)
    state = lib.create_ink_particles(state, x=100, y=100, count=3)
    assert len(set(state.ids.tolist())) == len(state.ids)


def test_create_ink_particles_default_count():
    # V1 create_ink_particles.md: count = 50.
    state = lib.create_chamber()
    state = lib.create_ink_particles(state, x=10, y=10)
    assert (state.types == "ink").sum() == 50


# ---------------------------------------------------------------------------
# advance_positions
# ---------------------------------------------------------------------------

def test_advance_positions_zero_dt_no_movement():
    state = make_state(n_water=4)
    moved = lib.advance_positions(state, dt=0.0)
    numpy.testing.assert_array_equal(moved.xs, state.xs)
    numpy.testing.assert_array_equal(moved.ys, state.ys)
    assert moved.tick == state.tick + 1


def test_advance_positions_known_motion():
    # 1 particle at origin, heading 0 (positive x), speed 10, dt 0.5.
    state = ParticleState(
        tick=0,
        ids=numpy.array([0], dtype=numpy.int64),
        types=numpy.array(["water"], dtype=object),
        xs=numpy.array([0.0]),
        ys=numpy.array([0.0]),
        headings=numpy.array([0.0]),
        speeds=numpy.array([10.0]),
        masses=numpy.array(["medium"], dtype=object),
        width=100.0, height=100.0,
    )
    moved = lib.advance_positions(state, dt=0.5)
    assert moved.xs[0] == pytest.approx(5.0)
    assert moved.ys[0] == pytest.approx(0.0)


def test_advance_positions_increments_tick():
    state = make_state(n_water=2)
    moved = lib.advance_positions(state, dt=0.1)
    assert moved.tick == state.tick + 1


# ---------------------------------------------------------------------------
# bounce_off_walls
# ---------------------------------------------------------------------------

def test_bounce_off_walls_left_wall_reflects_heading():
    state = ParticleState(
        tick=0,
        ids=numpy.array([0], dtype=numpy.int64),
        types=numpy.array(["water"], dtype=object),
        xs=numpy.array([-1.0]),  # past left wall
        ys=numpy.array([100.0]),
        headings=numpy.array([math.pi]),  # heading left (π)
        speeds=numpy.array([10.0]),
        masses=numpy.array(["medium"], dtype=object),
        width=200.0, height=200.0,
    )
    bounced = lib.bounce_off_walls(state)
    # π - π = 0 (mod 2π) — now heading right.
    assert bounced.headings[0] == pytest.approx(0.0)
    # Clamped to 0.
    assert bounced.xs[0] == 0.0


def test_bounce_off_walls_top_wall_reflects_heading():
    state = ParticleState(
        tick=0,
        ids=numpy.array([0], dtype=numpy.int64),
        types=numpy.array(["water"], dtype=object),
        xs=numpy.array([100.0]),
        ys=numpy.array([250.0]),  # past top
        headings=numpy.array([math.pi / 2]),  # heading up (+y)
        speeds=numpy.array([10.0]),
        masses=numpy.array(["medium"], dtype=object),
        width=200.0, height=200.0,
    )
    bounced = lib.bounce_off_walls(state)
    # -π/2 mod 2π = 3π/2 — now heading down.
    assert bounced.headings[0] == pytest.approx(3 * math.pi / 2)
    assert bounced.ys[0] == 200.0


def test_bounce_off_walls_inside_chamber_unchanged():
    state = make_state(n_water=3, width=200, height=200)
    bounced = lib.bounce_off_walls(state)
    numpy.testing.assert_array_equal(bounced.xs, state.xs)
    numpy.testing.assert_array_equal(bounced.ys, state.ys)
    numpy.testing.assert_allclose(bounced.headings, state.headings % (2 * math.pi))


# ---------------------------------------------------------------------------
# detect_collisions
# ---------------------------------------------------------------------------

def test_detect_collisions_empty_state():
    state = lib.create_chamber()
    pairs = lib.detect_collisions(state)
    assert pairs.shape == (0, 2)


def test_detect_collisions_single_particle():
    state = lib.create_chamber()
    state = lib.create_water_particles(state, count=1)
    assert lib.detect_collisions(state).shape == (0, 2)


def test_detect_collisions_two_approaching_particles():
    # Two particles within range, moving toward each other.
    state = ParticleState(
        tick=0,
        ids=numpy.array([0, 1], dtype=numpy.int64),
        types=numpy.array(["water", "water"], dtype=object),
        xs=numpy.array([0.0, 3.0]),
        ys=numpy.array([0.0, 0.0]),
        # Particle 0 heading right (+x), 1 heading left (π).
        headings=numpy.array([0.0, math.pi]),
        speeds=numpy.array([10.0, 10.0]),
        masses=numpy.array(["medium", "medium"], dtype=object),
        width=200.0, height=200.0,
    )
    pairs = lib.detect_collisions(state, radius=5.0)
    assert pairs.shape == (1, 2)
    assert pairs[0, 0] == 0 and pairs[0, 1] == 1


def test_detect_collisions_diverging_particles_filtered():
    # Two particles within range but moving apart — shrinking-separation
    # filter excludes them (V1 interact.md's 85.7% → 3.5% recurrence fix).
    state = ParticleState(
        tick=0,
        ids=numpy.array([0, 1], dtype=numpy.int64),
        types=numpy.array(["water", "water"], dtype=object),
        xs=numpy.array([0.0, 3.0]),
        ys=numpy.array([0.0, 0.0]),
        # Particle 0 heading left (π), 1 heading right (+x) — diverging.
        headings=numpy.array([math.pi, 0.0]),
        speeds=numpy.array([10.0, 10.0]),
        masses=numpy.array(["medium", "medium"], dtype=object),
        width=200.0, height=200.0,
    )
    pairs = lib.detect_collisions(state, radius=5.0)
    assert pairs.shape == (0, 2)


# ---------------------------------------------------------------------------
# bounce_off_pairs
# ---------------------------------------------------------------------------

def test_bounce_off_pairs_swaps_headings():
    state = ParticleState(
        tick=0,
        ids=numpy.array([0, 1], dtype=numpy.int64),
        types=numpy.array(["water", "water"], dtype=object),
        xs=numpy.array([0.0, 3.0]),
        ys=numpy.array([0.0, 0.0]),
        headings=numpy.array([0.1, 2.5]),
        speeds=numpy.array([10.0, 10.0]),
        masses=numpy.array(["medium", "medium"], dtype=object),
        width=200.0, height=200.0,
    )
    pairs = numpy.array([[0, 1]], dtype=numpy.int64)
    bounced = lib.bounce_off_pairs(state, pairs)
    assert bounced.headings[0] == pytest.approx(2.5)
    assert bounced.headings[1] == pytest.approx(0.1)


def test_bounce_off_pairs_empty_pairs_returns_state():
    state = make_state(n_water=3)
    empty_pairs = numpy.empty((0, 2), dtype=numpy.int64)
    bounced = lib.bounce_off_pairs(state, empty_pairs)
    numpy.testing.assert_array_equal(bounced.headings, state.headings)


def test_bounce_off_pairs_none_pairs_returns_state():
    state = make_state(n_water=3)
    bounced = lib.bounce_off_pairs(state, None)
    assert bounced is state


# ---------------------------------------------------------------------------
# set_speed_for_type / set_mass_for_type
# ---------------------------------------------------------------------------

def test_set_speed_for_type_updates_only_matching():
    state = make_state(n_water=3, n_ink=2, water_speed=50.0, ink_speed=50.0)
    updated = lib.set_speed_for_type(state, "water", 100.0)
    is_water = updated.types == "water"
    is_ink = updated.types == "ink"
    assert (updated.speeds[is_water] == 100.0).all()
    assert (updated.speeds[is_ink] == 50.0).all()


def test_set_speed_for_type_no_matches_no_change():
    state = make_state(n_water=2)
    updated = lib.set_speed_for_type(state, "lava", 999.0)
    numpy.testing.assert_array_equal(updated.speeds, state.speeds)


def test_set_mass_for_type_updates_only_matching():
    state = make_state(n_water=2, n_ink=2)
    updated = lib.set_mass_for_type(state, "ink", "heavy")
    is_ink = updated.types == "ink"
    is_water = updated.types == "water"
    assert (updated.masses[is_ink] == "heavy").all()
    assert (updated.masses[is_water] == "medium").all()


# ---------------------------------------------------------------------------
# group_clicks_by_tick / apply_clicks_at_tick
# ---------------------------------------------------------------------------

def test_group_clicks_by_tick_collects_by_key():
    clicks = [
        {"tick": 5, "x": 1.0, "y": 2.0},
        {"tick": 5, "x": 3.0, "y": 4.0},
        {"tick": 10, "x": 5.0, "y": 6.0},
    ]
    by_tick = lib.group_clicks_by_tick(clicks)
    assert by_tick[5] == [(1.0, 2.0), (3.0, 4.0)]
    assert by_tick[10] == [(5.0, 6.0)]


def test_group_clicks_by_tick_empty():
    assert lib.group_clicks_by_tick([]) == {}


def test_apply_clicks_at_tick_invokes_callback_per_event():
    calls = []

    def fake_on_click(state, x, y):
        calls.append((x, y))
        return state

    state = make_state(n_water=1)
    clicks_by_tick = {7: [(1.0, 2.0), (3.0, 4.0)]}
    lib.apply_clicks_at_tick(state, clicks_by_tick, tick=7,
                              on_click=fake_on_click)
    assert calls == [(1.0, 2.0), (3.0, 4.0)]


def test_apply_clicks_at_tick_no_clicks_passthrough():
    state = make_state(n_water=2)
    by_tick = {5: [(1.0, 2.0)]}
    out = lib.apply_clicks_at_tick(state, by_tick, tick=999)
    assert out is state


def test_apply_clicks_at_tick_default_on_click_creates_ink():
    state = lib.create_chamber()
    state = lib.create_water_particles(state, count=2)
    by_tick = {0: [(100.0, 100.0)]}
    out = lib.apply_clicks_at_tick(state, by_tick, tick=0)
    # Default on_click is create_ink_particles -> 50 ink particles added.
    assert (out.types == "ink").sum() == 50


# ---------------------------------------------------------------------------
# random_name
# ---------------------------------------------------------------------------

def test_random_name_length():
    assert len(lib.random_name(5)) == 5
    assert len(lib.random_name(1)) == 1
    assert len(lib.random_name(10)) == 10


def test_random_name_lowercase_ascii_only():
    name = lib.random_name(20)
    assert all("a" <= ch <= "z" for ch in name)


def test_random_name_default_length():
    assert len(lib.random_name()) == 5


# ---------------------------------------------------------------------------
# tick_range
# ---------------------------------------------------------------------------

def test_tick_range_returns_list():
    assert lib.tick_range(5) == [0, 1, 2, 3, 4]


def test_tick_range_zero_empty():
    assert lib.tick_range(0) == []


def test_tick_range_accepts_float_n():
    # E-- numeric literals may transpile to float; tick_range should
    # tolerate that without breaking the For-each loop.
    assert lib.tick_range(3.0) == [0, 1, 2]


# ---------------------------------------------------------------------------
# show_simulation
# ---------------------------------------------------------------------------

def test_show_simulation_returns_state_unchanged():
    # Engine-side passthrough; plugin-side wire-up is the follow-up
    # drain. The chip must round-trip state so compositions like
    # `Return Call [[show_simulation]] with state=final_state.` still
    # produce the final state.
    state = make_state(n_water=3, n_ink=2)
    out = lib.show_simulation(state)
    assert out is state


# ---------------------------------------------------------------------------
# executor wiring
# ---------------------------------------------------------------------------

def test_moda_chips_registered_in_executor_domain_globals():
    """All 14 chips reachable as bare names when `domains=["moda"]`."""
    from forge.core.executor import _domain_globals_for
    g = _domain_globals_for(["moda"])
    for name in (
        "temperature_to_speed", "create_chamber",
        "create_water_particles", "create_ink_particles",
        "advance_positions", "bounce_off_walls", "bounce_off_pairs",
        "detect_collisions",
        "set_speed_for_type", "set_mass_for_type",
        "group_clicks_by_tick", "apply_clicks_at_tick",
        "random_name", "show_simulation", "tick_range",
        # Existing names from _FORGE_MODA_NAMES still present.
        "Particle", "ParticleState",
    ):
        assert name in g, f"chip {name!r} missing from moda domain globals"
