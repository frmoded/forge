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
import re

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


def test_simulation_recipe_names_its_four_callees(moda_vault):
    """Drain 2026-08-20-1210(c) — replaces test_simulation_dependencies_block.

    That test asserted a trailing `# Dependencies` block whose wikilinks
    mirrored the Python facet's `context.compute()` calls. Both halves
    of that premise are V1: the shipping simulation.md has no
    `# Dependencies` section and no Python facet — it has Description
    and Recipe, and the Recipe IS where V2 declares dependencies.

    So the convention is retired, not broken, and the check moves to
    where the information now lives. The stronger half of the old
    guarantee — that these names actually resolve — is covered per-note
    by test_blocks_static.py::test_every_recipe_wikilink_resolves.
    """
    from pathlib import Path
    body = (Path(moda_vault) / "simulation.md").read_text()
    recipe, inside = [], False
    for line in body.splitlines():
        if line.startswith("# Recipe"):
            inside = True
            continue
        if inside and line.startswith("# "):
            break
        if inside:
            recipe.append(line)
    recipe_text = "\n".join(recipe)
    assert recipe_text.strip(), "simulation.md has no Recipe body to check"
    # Either citation form counts. Three are called as wikilinks;
    # `on_mouse_click` is passed BY NAME as a callable argument
    # (`on_click=on_mouse_click`), which is equally a dependency and
    # equally breaks if the note disappears.
    for callee in ["setup", "sample_clicks", "on_mouse_click", "go"]:
        cited = f"[[{callee}]]" in recipe_text or re.search(
            rf"\b{re.escape(callee)}\b", recipe_text)
        assert cited, (
            f"simulation.md's Recipe no longer references {callee!r}; "
            f"Recipe was: {recipe_text!r}")
