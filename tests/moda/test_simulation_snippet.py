"""Tests for the bounded-run `simulation` snippet shipped in
forge-moda v0.4.15.

`simulation` is a meta snippet that expresses the moda event-loop
wiring as a one-shot bounded action: setup → 300 ticks of go, with
clicks scheduled per the `sample_clicks` data snippet. The tests
exercise it through the engine's resolver + executor (the same path
the generic /compute endpoint uses internally), but assert directly
on the returned `ParticleState` rather than crossing the HTTP wire
— `serialize_result` doesn't yet wire-encode ParticleState through
the generic /compute response (separate `unify-compute-serialization`
work), so a TestClient roundtrip would 500 in the serialization
layer even though the snippet itself runs cleanly.
"""
import numpy as np


def test_simulation_returns_particle_state(run_block):
    """End-to-end happy path: 300 ticks of go with 3 scheduled
    clicks. Final state has tick == 300, the initial water
    population, and ink populations from each click."""
    state = run_block("simulation")
    assert state is not None
    # 300 go-ticks each advance tick by 1 inside move().
    assert state.tick == 300
    # setup creates 500 water particles; 3 clicks add 50 ink each.
    n_water = int((state.types == "water").sum())
    n_ink = int((state.types == "ink").sum())
    assert n_water == 500
    assert n_ink == 150


def test_simulation_respects_click_scenario(run_block):
    """The default sample_clicks has 3 clicks; absent its 150 ink
    particles, the run would terminate with only the 500-water
    setup population. Ink particles being present is the signal
    the click scenario was read and dispatched. Position checks
    are weak (ink disperses fast over 50-300 ticks of advection),
    but ink presence + count == 150 is a strong signal."""
    state = run_block("simulation")
    ink_mask = state.types == "ink"
    assert ink_mask.sum() == 150
    # All ink particles within the chamber after 300 ticks. Wall-
    # bounce keeps them bounded.
    assert state.xs[ink_mask].min() >= 0
    assert state.xs[ink_mask].max() <= state.width
    assert state.ys[ink_mask].min() >= 0
    assert state.ys[ink_mask].max() <= state.height


def test_simulation_dependencies_block(moda_vault):
    """The Dependencies block at the bottom of simulation.md
    resolves to the four expected wikilinks. B7 auto-sync would
    handle this on regen; here we assert the hand-authored shape
    matches the Python facet's actual context.compute() calls so
    the snippet ships consistent."""
    from pathlib import Path
    body = (Path(moda_vault) / "simulation.md").read_text()
    # The Dependencies section is the trailing block.
    deps_section = body.split("# Dependencies", 1)[1] if "# Dependencies" in body else ""
    for callee in ["setup", "sample_clicks", "on_mouse_click", "go"]:
        assert f"[[{callee}]]" in deps_section, (
            f"Dependencies block missing wikilink to {callee!r}; "
            f"section was: {deps_section!r}")
