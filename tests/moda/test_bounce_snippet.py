"""Behavioral test for the bounce_all_particles_off_walls snippet.

We exec_python a copy of the generated bounce code against a synthetic
state with deliberately out-of-bounds particles and assert that the
post-bounce positions are inside the canvas and the heading is
reflected. This catches a class of regressions in the bounce algorithm
itself (boundary condition flips, wrong axis reflection, missing
clamp) without depending on /generate or the LLM.

NOTE: the python below mirrors forge-moda/bounce_all_particles_off_walls.md
as of Phase 3. If the snippet is regenerated and the algorithm changes
materially, update this copy AND re-derive the expected post-conditions.
The smoke test in docs/smoke_test_phase3.md covers end-to-end correctness
against the live snippet.
"""
import math
import textwrap

import pytest

from forge.core.executor import exec_python
from forge.moda.types import Particle, ParticleState


# Mirrors the canonical generated Python in
# forge-moda/bounce_all_particles_off_walls.md (Phase 3).
_BOUNCE_PY = textwrap.dedent("""
    def compute(context, state):
        particles = state.particles
        if not particles:
            return ParticleState(tick=state.tick, particles=[],
                                 width=state.width, height=state.height)

        ids = numpy.array([p.id for p in particles])
        types = [p.type for p in particles]
        masses = [p.mass for p in particles]
        xs = numpy.array([p.x for p in particles], dtype=float)
        ys = numpy.array([p.y for p in particles], dtype=float)
        headings = numpy.array([p.heading for p in particles], dtype=float)
        speeds = numpy.array([p.speed for p in particles], dtype=float)

        w = state.width
        h = state.height

        hit_x = (xs < 0) | (xs > w)
        hit_y = (ys < 0) | (ys > h)

        headings = numpy.where(hit_x, math.pi - headings, headings)
        headings = numpy.where(hit_y, -headings, headings)
        headings = headings % (2 * math.pi)

        xs = numpy.clip(xs, 0, w)
        ys = numpy.clip(ys, 0, h)

        updated = [
            Particle(id=int(ids[i]), type=types[i], x=float(xs[i]),
                     y=float(ys[i]), heading=float(headings[i]),
                     speed=float(speeds[i]), mass=masses[i])
            for i in range(len(particles))
        ]

        return ParticleState(tick=state.tick, particles=updated,
                             width=state.width, height=state.height)
""")


W = 100.0
H = 100.0


def _run_bounce(state):
  _, result = exec_python(_BOUNCE_PY, inputs={}, args=(state,))
  return result


def test_bounce_pulls_all_corners_back_in_bounds():
  """8 particles out of bounds in all 4 cardinal + 4 corner directions
  must all return inside the canvas."""
  particles = [
    # Left of x=0
    Particle(id=0, type="water", x=-5.0, y=50.0,
             heading=math.pi, speed=10.0, mass="medium"),
    # Right of x=W
    Particle(id=1, type="water", x=W + 5.0, y=50.0,
             heading=0.0, speed=10.0, mass="medium"),
    # Above y=0
    Particle(id=2, type="water", x=50.0, y=-5.0,
             heading=-math.pi / 2, speed=10.0, mass="medium"),
    # Below y=H
    Particle(id=3, type="water", x=50.0, y=H + 5.0,
             heading=math.pi / 2, speed=10.0, mass="medium"),
    # Four corners
    Particle(id=4, type="water", x=-5.0, y=-5.0,
             heading=5 * math.pi / 4, speed=10.0, mass="medium"),
    Particle(id=5, type="water", x=W + 5.0, y=-5.0,
             heading=7 * math.pi / 4, speed=10.0, mass="medium"),
    Particle(id=6, type="water", x=-5.0, y=H + 5.0,
             heading=3 * math.pi / 4, speed=10.0, mass="medium"),
    Particle(id=7, type="water", x=W + 5.0, y=H + 5.0,
             heading=math.pi / 4, speed=10.0, mass="medium"),
  ]
  state = ParticleState(tick=42, particles=particles, width=W, height=H)

  out = _run_bounce(state)

  for p in out.particles:
    assert 0.0 <= p.x <= W, f"particle {p.id} x={p.x} not in [0,{W}]"
    assert 0.0 <= p.y <= H, f"particle {p.id} y={p.y} not in [0,{H}]"


def test_bounce_does_not_advance_tick():
  """move advances tick; bounce only corrects state. Tick stays put."""
  particles = [Particle(id=0, type="water", x=-1.0, y=50.0,
                        heading=math.pi, speed=10.0, mass="medium")]
  state = ParticleState(tick=99, particles=particles, width=W, height=H)
  out = _run_bounce(state)
  assert out.tick == 99


def test_bounce_reflects_heading_off_vertical_wall():
  """A particle headed left (heading=π) into x<0 should flip to heading=0
  after bounce (π - π = 0)."""
  p = Particle(id=0, type="water", x=-1.0, y=50.0,
               heading=math.pi, speed=10.0, mass="medium")
  state = ParticleState(tick=0, particles=[p], width=W, height=H)
  out = _run_bounce(state)
  # π - π = 0, mod 2π = 0
  assert out.particles[0].heading == pytest.approx(0.0)


def test_bounce_reflects_heading_off_horizontal_wall():
  """A particle headed down-right with y>H should flip y-component:
  heading=π/4 → -π/4 (=7π/4 after mod)."""
  p = Particle(id=0, type="water", x=50.0, y=H + 1.0,
               heading=math.pi / 4, speed=10.0, mass="medium")
  state = ParticleState(tick=0, particles=[p], width=W, height=H)
  out = _run_bounce(state)
  expected = (-math.pi / 4) % (2 * math.pi)
  assert out.particles[0].heading == pytest.approx(expected)


def test_bounce_is_noop_for_in_bounds_particles():
  """A particle comfortably inside the canvas comes out unchanged
  (positions and heading exactly preserved, mod the heading wrap)."""
  p = Particle(id=0, type="water", x=42.0, y=37.0,
               heading=1.2, speed=10.0, mass="medium")
  state = ParticleState(tick=5, particles=[p], width=W, height=H)
  out = _run_bounce(state)
  assert out.particles[0].x == 42.0
  assert out.particles[0].y == 37.0
  assert out.particles[0].heading == pytest.approx(1.2)


def test_bounce_preserves_speed_and_mass():
  p = Particle(id=0, type="water", x=-5.0, y=50.0,
               heading=math.pi, speed=33.3, mass="heavy")
  state = ParticleState(tick=0, particles=[p], width=W, height=H)
  out = _run_bounce(state)
  assert out.particles[0].speed == 33.3
  assert out.particles[0].mass == "heavy"


def test_bounce_handles_empty_particle_list():
  state = ParticleState(tick=7, particles=[], width=W, height=H)
  out = _run_bounce(state)
  assert out.particles == []
  assert out.tick == 7
  assert out.width == W and out.height == H
