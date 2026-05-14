"""Behavioral test for the bounce_all_particles_off_walls snippet.

We exec_python a copy of the generated bounce code against a synthetic
state with deliberately out-of-bounds particles and assert that the
post-bounce positions are inside the canvas and the heading is
reflected. This catches a class of regressions in the bounce algorithm
itself (boundary condition flips, wrong axis reflection, missing
clamp) without depending on /generate or the LLM.

NOTE: the python below mirrors forge-moda/bounce_all_particles_off_walls.md
as of Phase 7 — ParticleState now stores per-particle fields as
parallel numpy arrays (struct-of-arrays). If the snippet is regenerated
and the algorithm changes materially, update this copy AND re-derive
the expected post-conditions. The smoke test in docs/smoke_test_phase3.md
covers end-to-end correctness against the live snippet.
"""
import math
import textwrap

import numpy as np
import pytest

from forge.core.executor import exec_python
from forge.moda.types import ParticleState


# Mirrors the canonical generated Python in
# forge-moda/bounce_all_particles_off_walls.md (Phase 7).
_BOUNCE_PY = textwrap.dedent("""
    def compute(context, state):
        hit_x = (state.xs < 0) | (state.xs > state.width)
        hit_y = (state.ys < 0) | (state.ys > state.height)

        new_headings = numpy.where(hit_x, math.pi - state.headings, state.headings)
        new_headings = numpy.where(hit_y, -new_headings, new_headings)
        new_headings = new_headings % (2 * math.pi)

        new_xs = numpy.clip(state.xs, 0, state.width)
        new_ys = numpy.clip(state.ys, 0, state.height)

        return ParticleState(
            tick=state.tick,
            ids=state.ids,
            types=state.types,
            xs=new_xs,
            ys=new_ys,
            headings=new_headings,
            speeds=state.speeds,
            masses=state.masses,
            width=state.width,
            height=state.height,
        )
""")


W = 100.0
H = 100.0


def _state(rows, tick=0, w=W, h=H):
  """Build a Phase-7-shape ParticleState from a list of per-row dicts.
  Each row: {id, type, x, y, heading, speed, mass}."""
  n = len(rows)
  ids = np.array([r["id"] for r in rows], dtype=np.int64) if n else np.empty((0,), dtype=np.int64)
  types = np.array([r["type"] for r in rows], dtype=object) if n else np.empty((0,), dtype=object)
  xs = np.array([r["x"] for r in rows], dtype=np.float64) if n else np.empty((0,), dtype=np.float64)
  ys = np.array([r["y"] for r in rows], dtype=np.float64) if n else np.empty((0,), dtype=np.float64)
  headings = np.array([r["heading"] for r in rows], dtype=np.float64) if n else np.empty((0,), dtype=np.float64)
  speeds = np.array([r["speed"] for r in rows], dtype=np.float64) if n else np.empty((0,), dtype=np.float64)
  masses = np.array([r["mass"] for r in rows], dtype=object) if n else np.empty((0,), dtype=object)
  return ParticleState(
    tick=tick, ids=ids, types=types, xs=xs, ys=ys,
    headings=headings, speeds=speeds, masses=masses,
    width=w, height=h,
  )


def _run_bounce(state):
  _, result = exec_python(_BOUNCE_PY, inputs={}, args=(state,))
  return result


def test_bounce_pulls_all_corners_back_in_bounds():
  """8 particles out of bounds in all 4 cardinal + 4 corner directions
  must all return inside the canvas."""
  rows = [
    # Left of x=0
    {"id": 0, "type": "water", "x": -5.0, "y": 50.0, "heading": math.pi, "speed": 10.0, "mass": "medium"},
    # Right of x=W
    {"id": 1, "type": "water", "x": W + 5.0, "y": 50.0, "heading": 0.0, "speed": 10.0, "mass": "medium"},
    # Above y=0
    {"id": 2, "type": "water", "x": 50.0, "y": -5.0, "heading": -math.pi / 2, "speed": 10.0, "mass": "medium"},
    # Below y=H
    {"id": 3, "type": "water", "x": 50.0, "y": H + 5.0, "heading": math.pi / 2, "speed": 10.0, "mass": "medium"},
    # Four corners
    {"id": 4, "type": "water", "x": -5.0, "y": -5.0, "heading": 5 * math.pi / 4, "speed": 10.0, "mass": "medium"},
    {"id": 5, "type": "water", "x": W + 5.0, "y": -5.0, "heading": 7 * math.pi / 4, "speed": 10.0, "mass": "medium"},
    {"id": 6, "type": "water", "x": -5.0, "y": H + 5.0, "heading": 3 * math.pi / 4, "speed": 10.0, "mass": "medium"},
    {"id": 7, "type": "water", "x": W + 5.0, "y": H + 5.0, "heading": math.pi / 4, "speed": 10.0, "mass": "medium"},
  ]
  state = _state(rows, tick=42)

  out = _run_bounce(state)

  for i in range(out.ids.shape[0]):
    assert 0.0 <= out.xs[i] <= W, f"particle {int(out.ids[i])} x={out.xs[i]} not in [0,{W}]"
    assert 0.0 <= out.ys[i] <= H, f"particle {int(out.ids[i])} y={out.ys[i]} not in [0,{H}]"


def test_bounce_does_not_advance_tick():
  """move advances tick; bounce only corrects state. Tick stays put."""
  state = _state(
    [{"id": 0, "type": "water", "x": -1.0, "y": 50.0,
      "heading": math.pi, "speed": 10.0, "mass": "medium"}],
    tick=99,
  )
  out = _run_bounce(state)
  assert out.tick == 99


def test_bounce_reflects_heading_off_vertical_wall():
  """A particle headed left (heading=π) into x<0 should flip to heading=0
  after bounce (π - π = 0)."""
  state = _state(
    [{"id": 0, "type": "water", "x": -1.0, "y": 50.0,
      "heading": math.pi, "speed": 10.0, "mass": "medium"}],
  )
  out = _run_bounce(state)
  # π - π = 0, mod 2π = 0
  assert out.headings[0] == pytest.approx(0.0)


def test_bounce_reflects_heading_off_horizontal_wall():
  """A particle headed down-right with y>H should flip y-component:
  heading=π/4 → -π/4 (=7π/4 after mod)."""
  state = _state(
    [{"id": 0, "type": "water", "x": 50.0, "y": H + 1.0,
      "heading": math.pi / 4, "speed": 10.0, "mass": "medium"}],
  )
  out = _run_bounce(state)
  expected = (-math.pi / 4) % (2 * math.pi)
  assert out.headings[0] == pytest.approx(expected)


def test_bounce_is_noop_for_in_bounds_particles():
  """A particle comfortably inside the canvas comes out unchanged
  (positions and heading exactly preserved, mod the heading wrap)."""
  state = _state(
    [{"id": 0, "type": "water", "x": 42.0, "y": 37.0,
      "heading": 1.2, "speed": 10.0, "mass": "medium"}],
    tick=5,
  )
  out = _run_bounce(state)
  assert out.xs[0] == 42.0
  assert out.ys[0] == 37.0
  assert out.headings[0] == pytest.approx(1.2)


def test_bounce_preserves_speed_and_mass():
  state = _state(
    [{"id": 0, "type": "water", "x": -5.0, "y": 50.0,
      "heading": math.pi, "speed": 33.3, "mass": "heavy"}],
  )
  out = _run_bounce(state)
  assert out.speeds[0] == 33.3
  assert out.masses[0] == "heavy"


def test_bounce_handles_empty_particle_list():
  state = _state([], tick=7)
  out = _run_bounce(state)
  assert out.ids.shape == (0,)
  assert out.xs.shape == (0,)
  assert out.tick == 7
  assert out.width == W and out.height == H
