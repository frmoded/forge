"""Static conformance for the 25 MoDa block snippets.

For each block, assert the generated Python:
  - parses,
  - has the expected `compute` signature (implicit-state convention:
    `compute(context, state, <declared inputs>)`, except `setup`
    which is the state-origin: `compute(context, temperature)`),
  - calls exactly the peer snippets its English names (catches
    hallucinated deps like the `get_colliding_pairs` slip),
  - is vectorized where it does per-particle/per-pair work, and never
    Python-loops over the particle arrays.
"""
import ast
import re

import pytest

# block id -> (extra params after the implicit `state`, expected
# context.compute peer ids (exact set), must_be_vectorized)
SPEC = {
    # setup chain
    "setup": (["temperature"], {"create_water_particles", "set_water_speed", "set_water_mass"}, False),
    "create_water_particles": ([], set(), True),
    "set_water_speed": (["temperature"], {"speed_for_temperature"}, True),
    "set_water_mass": ([], set(), True),
    # click chain
    "on_mouse_click": (["x", "y"], {"create_ink_particles", "set_ink_speed", "set_ink_mass"}, False),
    "create_ink_particles": (["x", "y"], set(), True),
    "set_ink_speed": ([], {"speed_for_temperature"}, True),
    "set_ink_mass": ([], set(), True),
    # go chain
    "go": (["dt", "temperature"], {"ask_all_particles", "ask_water_particles"}, False),
    "ask_all_particles": (["dt"], {"move", "if_wall_then_bounce", "interact"}, False),
    "move": (["dt"], set(), True),
    "interact": ([], {"if_particle_then_bounce"}, True),
    "if_wall_then_bounce": ([], {"bounce_off_wall"}, False),
    "bounce_off_wall": ([], set(), True),
    "if_particle_then_bounce": (["pairs"], {"bounce_off_particle"}, False),
    "bounce_off_particle": (["pairs"], set(), True),
    # temperature chain
    "ask_water_particles": (["temperature"], {
        "if_temp_high_set_speed", "if_temp_medium_set_speed",
        "if_temp_low_set_speed", "if_temp_zero_set_speed"}, False),
    "if_temp_high_set_speed": (["temperature"], {"set_speed_high"}, False),
    "set_speed_high": ([], {"speed_for_temperature"}, True),
    "if_temp_medium_set_speed": (["temperature"], {"set_speed_medium"}, False),
    "set_speed_medium": ([], {"speed_for_temperature"}, True),
    "if_temp_low_set_speed": (["temperature"], {"set_speed_low"}, False),
    "set_speed_low": ([], {"speed_for_temperature"}, True),
    "if_temp_zero_set_speed": (["temperature"], {"set_speed_zero"}, False),
    "set_speed_zero": ([], {"speed_for_temperature"}, True),
}

# setup is the state origin — no `state` parameter.
_NO_STATE = {"setup"}

_PARTICLE_LOOP = re.compile(
    r"\bfor\s+\w+\s+in\s+(state\.|range\(\s*len\(\s*state\.|range\(\s*state\.)"
)
# A vectorized block operates on the struct-of-arrays fields directly.
# Boolean-mask / fancy-index code (`state.types == 'water'`,
# `speeds[is_water] = ...`) is vectorized but carries NO literal
# `numpy.` token — so "touches a state array" + "no particle loop"
# (asserted globally) is the faithful vectorization signal here.
_STATE_ARRAY = re.compile(r"\bstate\.(xs|ys|headings|speeds|types|masses|ids)\b")


def _find_compute(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "compute":
            return node
    return None


def _compute_call_targets(tree):
    targets = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "compute"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "context"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            targets.add(node.args[0].value)
    return targets


@pytest.mark.parametrize("sid", sorted(SPEC))
def test_block_static_conformance(sid, block_source):
    extra, expected_peers, must_vec = SPEC[sid]
    src = block_source(sid)
    assert src and src.strip(), f"{sid}: empty Python facet"

    tree = ast.parse(src)  # raises SyntaxError -> test failure
    fn = _find_compute(tree)
    assert fn is not None, f"{sid}: no compute() defined"

    params = [a.arg for a in fn.args.args]
    if sid in _NO_STATE:
        expected = ["context"] + extra
    else:
        expected = ["context", "state"] + extra
    assert params == expected, (
        f"{sid}: signature {params} != expected {expected}")

    peers = _compute_call_targets(tree)
    assert peers == expected_peers, (
        f"{sid}: context.compute targets {peers} != expected "
        f"{expected_peers} (extra = hallucinated/missing dep)")

    # No block — dispatch or action — may Python-loop the particle arrays.
    assert not _PARTICLE_LOOP.search(src), (
        f"{sid}: Python loop over particle arrays detected; must vectorize")

    if must_vec:
        assert _STATE_ARRAY.search(src), (
            f"{sid}: per-particle/per-pair block must operate on the "
            f"struct-of-arrays state fields (state.xs / types / speeds / "
            f"...); none referenced")
