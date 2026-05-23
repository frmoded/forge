"""Light integration for the MoDa block chains.

Each test runs real block snippets against a hand-crafted ParticleState
and asserts the block's semantics. Uses the session-scoped `run_block`
fixture (resolves snippets from the moda vault, lives in conftest.py)
and the `make_state` helper (a plain function in _helpers.py).
"""
import math

import numpy as np
import pytest

from tests.moda._helpers import make_state


# ---------------------------------------------------------------------------
# Setup chain (blocks 1–4)
# ---------------------------------------------------------------------------

def test_setup_creates_500_water_at_medium(run_block):
    s = run_block("setup", "medium")
    assert s.tick == 0
    assert len(s.ids) == 500
    assert (s.types == "water").all()
    assert s.width == 800.0 and s.height == 600.0
    # set_water_speed @ medium -> 50, set_water_mass -> medium
    assert sorted(set(np.round(s.speeds, 3))) == [50.0]
    assert set(s.masses.tolist()) == {"medium"}
    assert (s.xs >= 0).all() and (s.xs <= s.width).all()
    assert (s.ys >= 0).all() and (s.ys <= s.height).all()


def test_setup_temperature_threads_into_initial_speed(run_block):
    assert sorted(set(np.round(run_block("setup", "zero").speeds, 3))) == [0.0]
    assert sorted(set(np.round(run_block("setup", "high").speeds, 3))) == [100.0]


def test_create_water_particles_appends_to_state(run_block):
    s0 = make_state(n_water=3, n_ink=2)
    s1 = run_block("create_water_particles", s0)
    assert len(s1.ids) == 5 + 500
    # ids continue past the existing max
    assert s1.ids.max() == 504
    assert (s1.types[5:] == "water").all()


# ---------------------------------------------------------------------------
# Click chain (blocks 5–8)
# ---------------------------------------------------------------------------

def test_on_mouse_click_adds_50_ink_as_a_radial_drop(run_block):
    """v0.4.13: ink spawns disperse radially from the click point —
    each particle gets a small position jitter (within ±3 units of
    the click) and its own random heading uniform in [0, 2π). The
    previous "coherent puff" with a shared heading was pedagogically
    misleading (ink dropped in water disperses; it doesn't migrate
    as one cohesive body)."""
    s0 = make_state(n_water=10)
    s1 = run_block("on_mouse_click", s0, 400.0, 300.0)
    assert len(s1.ids) == 60
    ink = s1.types == "ink"
    assert ink.sum() == 50
    # Position jitter: ±3 units of the click. Not all-equal — that
    # would mean we lost the per-particle randomness.
    assert s1.xs[ink].min() >= 400.0 - 3.0
    assert s1.xs[ink].max() <= 400.0 + 3.0
    assert s1.ys[ink].min() >= 300.0 - 3.0
    assert s1.ys[ink].max() <= 300.0 + 3.0
    assert not np.allclose(s1.xs[ink], 400.0)  # not all identical
    assert not np.allclose(s1.ys[ink], 300.0)
    # Per-particle headings: many distinct values, not a single
    # shared one. 50 uniform draws on [0, 2π) should easily yield
    # >40 distinct values at float64 precision.
    assert len(set(np.round(s1.headings[ink], 9))) >= 40
    # set_ink_speed -> medium constant overwrites the per-particle
    # spawn speed; downstream invariant preserved.
    assert sorted(set(np.round(s1.speeds[ink], 3))) == [50.0]
    assert set(s1.masses[ink].tolist()) == {"medium"}
    # water rows untouched
    assert (s1.types[:10] == "water").all()


# ---------------------------------------------------------------------------
# Movement / collision blocks (10–16)
# ---------------------------------------------------------------------------

def test_move_advances_position_and_tick(run_block):
    s0 = make_state(n_water=4, water_speed=30.0, seed=1)
    x0, y0, h = s0.xs.copy(), s0.ys.copy(), s0.headings.copy()
    s1 = run_block("move", s0, 0.1)
    assert s1.tick == s0.tick + 1
    np.testing.assert_allclose(s1.xs, x0 + 30.0 * np.cos(h) * 0.1, rtol=1e-9)
    np.testing.assert_allclose(s1.ys, y0 + 30.0 * np.sin(h) * 0.1, rtol=1e-9)
    np.testing.assert_array_equal(s1.headings, h)  # heading unchanged by move


def test_bounce_off_wall_clamps_and_reflects(run_block):
    s = make_state(n_water=4)
    # Force two out-of-bounds particles
    s.xs[0] = -5.0
    s.headings[0] = math.pi  # heading into the left wall
    s.ys[1] = s.height + 7.0
    s.headings[1] = math.pi / 4
    out = run_block("bounce_off_wall", s)
    assert (out.xs >= 0).all() and (out.xs <= out.width).all()
    assert (out.ys >= 0).all() and (out.ys <= out.height).all()
    # vertical-wall reflection: pi - pi == 0 (mod 2pi)
    assert out.headings[0] == pytest.approx(0.0)
    # horizontal-wall reflection of pi/4 -> -pi/4 (== 7pi/4 mod 2pi)
    assert out.headings[1] == pytest.approx((-math.pi / 4) % (2 * math.pi))


def test_interact_swaps_headings_for_approaching_overlap(run_block):
    # Two particles 3 units apart (< 5), closing on each other along x.
    s = make_state(n_water=2)
    s.xs[:] = [100.0, 103.0]
    s.ys[:] = [100.0, 100.0]
    s.speeds[:] = [10.0, 10.0]
    s.headings[:] = [0.0, math.pi]      # i -> +x, j -> -x : approaching
    h0 = s.headings.copy()
    out = run_block("interact", s)
    # headings swapped within the colliding pair
    assert out.headings[0] == pytest.approx(h0[1])
    assert out.headings[1] == pytest.approx(h0[0])
    # speed (hence KE) preserved exactly
    np.testing.assert_array_equal(out.speeds, s.speeds)


def test_interact_ignores_separating_pair(run_block):
    # Within 5 units but moving apart -> approach filter rejects (Phase-5
    # anti-cluster fix, preserved per decision 2a).
    s = make_state(n_water=2)
    s.xs[:] = [100.0, 103.0]
    s.ys[:] = [100.0, 100.0]
    s.speeds[:] = [10.0, 10.0]
    s.headings[:] = [math.pi, 0.0]      # i -> -x, j -> +x : separating
    h0 = s.headings.copy()
    out = run_block("interact", s)
    np.testing.assert_array_equal(out.headings, h0)  # no swap


# ---------------------------------------------------------------------------
# Temperature chain (blocks 17–25)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("temp,expected", [
    ("zero", 0.0), ("low", 20.0), ("medium", 50.0), ("high", 100.0),
])
def test_ask_water_particles_sets_water_speed_only(run_block, temp, expected):
    s = make_state(n_water=6, n_ink=4, water_speed=999.0, ink_speed=50.0)
    out = run_block("ask_water_particles", s, temp)
    water = out.types == "water"
    ink = out.types == "ink"
    assert sorted(set(np.round(out.speeds[water], 3))) == [expected]
    # ink is temperature-immune
    np.testing.assert_array_equal(out.speeds[ink], s.speeds[ink])


def test_if_temp_branch_is_a_noop_when_unmatched(run_block):
    s = make_state(n_water=3, water_speed=42.0)
    # temperature is "low" but we invoke the high branch -> unchanged
    out = run_block("if_temp_high_set_speed", s, "low")
    np.testing.assert_array_equal(out.speeds, s.speeds)
