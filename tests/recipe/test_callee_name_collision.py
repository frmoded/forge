"""Codegen must be collision-proof against local names. Drain 1610.

CCQA's check-4, reproducing every time: when the LLM names a `Let`
variable identically to the callee, the transpiler emitted

    greeting = greeting()

Python makes a name local for the WHOLE function body as soon as it is
assigned anywhere, so the local shadows the callable and the call dies.
The closure inference was correct; only the codegen was wrong.

WHY THE LOCAL IS RENAMED RATHER THAN THE CALLEE ALIASED. That same
scoping rule rules out aliasing: `_c = greeting` placed BEFORE the
assignment also reads the unbound local. Any alias must bind outside the
body, which means touching `compute`'s signature — and that signature is
the kwargs contract the strip and the engine call against. Renaming the
local is invisible to every caller.

The scheme is a trailing underscore, PEP 8's own idiom for exactly this,
because it keeps the word the cohort chose visible in a facet they read.
"""
from __future__ import annotations

import pytest

from pathlib import Path

from forge.recipe.parser import parse
from forge.recipe.transpiler import transpile

_REPO = Path(__file__).resolve().parents[2]


def _run(src: str, shims: dict, **kwargs):
  """Transpile and execute, with the callables bound the way the real
  execution scope binds them — as module globals."""
  py = transpile(parse(src))
  ns = dict(shims)
  exec(compile(py, "<gen>", "exec"), ns)
  return ns["compute"](None, **kwargs)


GREET = {"greeting": lambda **k: "hello!"}


# ---------- CCQA's exact shape ----------------------------------------

def test_ccqa_shape_transpiles_without_shadowing():
  py = transpile(parse("Let greeting = Call [[greeting]].\nReturn greeting."))
  assert "greeting = greeting()" not in py, (
    "the local still shadows the callable — this is the reported bug"
  )
  assert "greeting_ = greeting()" in py
  assert "return greeting_" in py


def test_ccqa_shape_actually_runs():
  # The half a codegen-only assertion cannot see.
  assert _run("Let greeting = Call [[greeting]].\nReturn greeting.", GREET) == "hello!"


# ---------- non-vacuity: no gratuitous renames ------------------------

NON_COLLIDING_CORPUS = [
  "Let g = Call [[greeting]].\nReturn g.",
  "Let x = 1.\nLet y = x + 2.\nReturn y.",
  'Input n: int = 5.\nLet doubled = n * 2.\nReturn doubled.',
  "Let xs = [1, 2].\nFor each item in xs:\n  Return item.\nReturn 0.",
  'Let a = Call [[greet]] with name="ada".\nReturn a.',
  "Let n = 1.\nIf n > 0:\n  Return 1.\nReturn 0.",
]


@pytest.mark.parametrize("src", NON_COLLIDING_CORPUS)
def test_non_colliding_output_is_byte_identical_to_pre_drain(src):
  """§2 — generated Python is COMMITTED content. A rename that fired on
  a non-colliding name would dirty every synced note's lineage.

  Compared against the transpiler AS IT WAS BEFORE this drain, loaded
  from git, rather than against strings I typed out — a hand-written
  expectation only proves I typed what the code does today.
  """
  import subprocess, sys, types
  before_src = subprocess.run(
    ["git", "show", "HEAD:forge/recipe/transpiler.py"],
    cwd=str(_REPO), capture_output=True, text=True, check=True).stdout
  mod = types.ModuleType("_transpiler_before")
  mod.__file__ = str(_REPO / "forge" / "recipe" / "transpiler.py")
  mod.__package__ = "forge.recipe"
  exec(compile(before_src, mod.__file__, "exec"), mod.__dict__)
  assert transpile(parse(src)) == mod.transpile(parse(src))


def test_the_byte_identical_check_would_notice_a_change():
  """NON-VACUITY for the corpus above: the pre-drain transpiler must
  DISAGREE on the colliding shape, or the comparison proves nothing."""
  import subprocess, types
  before_src = subprocess.run(
    ["git", "show", "HEAD:forge/recipe/transpiler.py"],
    cwd=str(_REPO), capture_output=True, text=True, check=True).stdout
  mod = types.ModuleType("_transpiler_before2")
  mod.__file__ = str(_REPO / "forge" / "recipe" / "transpiler.py")
  mod.__package__ = "forge.recipe"
  exec(compile(before_src, mod.__file__, "exec"), mod.__dict__)
  collide = "Let greeting = Call [[greeting]].\nReturn greeting."
  assert mod.transpile(parse(collide)) != transpile(parse(collide))


def test_a_local_that_shares_no_callee_name_is_untouched():
  py = transpile(parse("Let greeting = 1.\nReturn greeting."))
  assert "greeting = 1" in py, "renamed a local with nothing to collide with"
  assert "greeting_" not in py


# ---------- the other collision positions §1 names --------------------

def test_kwarg_position_collision():
  src = "Let greeting = Call [[other]] with x=Call [[greeting]].\nReturn greeting."
  py = transpile(parse(src))
  assert "x=greeting()" in py, "the callee in kwarg position must stay callable"
  assert "greeting_ = other(" in py
  out = _run(src, {**GREET, "other": lambda **k: f"other({k['x']})"})
  assert out == "other(hello!)"


def test_for_each_loop_variable_collision():
  src = ("Let xs = [1].\nFor each greeting in xs:\n"
         "  Let r = Call [[greeting]].\n  Return r.\nReturn 0.")
  py = transpile(parse(src))
  assert "for greeting_ in xs:" in py
  assert "r = greeting()" in py, "the callee must survive the loop variable"
  assert _run(src, GREET) == "hello!"


def test_input_collision_routes_around_the_parameter():
  """An Input CANNOT be renamed — it is the kwargs contract — and the
  parameter shadows the callable for the whole body. So the call goes
  through the globals the execution scope binds the shim into."""
  src = 'Input greeting: str = "hi".\nLet r = Call [[greeting]].\nReturn r.'
  py = transpile(parse(src))
  assert "def compute(context, greeting: str = 'hi')" in py, (
    "the Input parameter name is the wire contract and must not change"
  )
  assert "globals()['greeting']()" in py
  assert _run(src, GREET) == "hello!"
  # And the kwarg still lands under its declared name.
  assert _run(src, GREET, greeting="ignored") == "hello!"


# ---------- multiple + nested collisions ------------------------------

def test_multiple_distinct_collisions():
  src = ("Let greeting = Call [[greeting]].\n"
         "Let farewell = Call [[farewell]].\n"
         "Return farewell.")
  py = transpile(parse(src))
  assert "greeting_ = greeting()" in py
  assert "farewell_ = farewell()" in py
  out = _run(src, {**GREET, "farewell": lambda **k: "bye!"})
  assert out == "bye!"


def test_rename_avoids_a_name_already_taken():
  """`greeting_` must not be handed out if the Recipe already uses it."""
  src = ("Let greeting_ = 1.\n"
         "Let greeting = Call [[greeting]].\n"
         "Return greeting.")
  py = transpile(parse(src))
  assert "greeting_ = 1" in py, "the existing local keeps its name"
  assert "greeting__ = greeting()" in py, "the collision escalates instead of clashing"


def test_nested_collision_inside_a_conditional():
  src = ("Let n = 1.\n"
         "If n > 0:\n"
         "  Let greeting = Call [[greeting]].\n"
         "  Return greeting.\n"
         "Return 0.")
  py = transpile(parse(src))
  assert "greeting_ = greeting()" in py
  assert _run(src, GREET) == "hello!"


# ---------- scope ------------------------------------------------------

def test_path_shaped_callees_cannot_collide():
  """A qualified callee routes through context.compute() and never
  appears as a bare name, so it needs no protection — and must not
  trigger a rename."""
  src = "Let solitary = Call [[music-core/percussion_lab/solitary]].\nReturn solitary."
  py = transpile(parse(src))
  assert "solitary = context.compute(" in py
  assert "solitary_" not in py
