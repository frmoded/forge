"""V2 E-- transpiler tests — AST → Python source. Verifies the shape of
the generated Python and that it actually executes correctly with a
chip registry."""

from forge.recipe import parse, transpile


def _wrap_and_exec(emm_src, chip_registry):
  """Helper: parse + transpile + exec, returning the compute() result.

  Chips are injected as named globals directly (mirroring the executor's
  music-domain shim mechanism). The transpiler emits direct function
  calls, so `kick` just needs to be a name in scope.
  """
  py_src = transpile(parse(emm_src))
  scope = dict(chip_registry)
  exec(py_src, scope)
  return scope["compute"](context=None)


class TestTranspile:
  def test_empty_recipe_emits_pass_body(self):
    # Drain 2026-07-02-1900 regression: newly-created V2 notes ship
    # with an empty Recipe body (per the v0.2.232 template). The
    # transpile pipeline must handle this without throwing — empty
    # module → `def compute(context): pass`. The plugin's
    # togglePythonVisibility path uses this to materialize a stub
    # Python facet on a fresh note.
    py = transpile(parse(""))
    assert "def compute(context):" in py
    assert "pass" in py

  def test_let_return(self):
    py = transpile(parse("Let x = 1.\nReturn x."))
    assert "def compute(context):" in py
    assert "x = 1" in py
    assert "return x" in py

  def test_bare_return(self):
    py = transpile(parse("Return."))
    assert "return None" in py

  def test_chip_call_kwargs(self):
    py = transpile(parse("Let r = Call [[add]] with a=1, b=2."))
    assert "add(a=1, b=2)" in py

  def test_shorthand_call_no_arg(self):
    py = transpile(parse("[[reset]]."))
    assert "reset()" in py

  def test_shorthand_call_with_arg(self):
    py = transpile(parse("[[show]] x."))
    assert "show(x)" in py

  def test_list_literal(self):
    py = transpile(parse("Let xs = [1, 2, 3]."))
    assert "xs = [1, 2, 3]" in py

  def test_repeat(self):
    py = transpile(parse(
      "Repeat 3 times:\n"
      "  Let x = 1.\n"
    ))
    assert "for _ in range(3):" in py
    assert "x = 1" in py

  def test_foreach(self):
    py = transpile(parse(
      "For each n in [1, 2, 3]:\n"
      "  Let y = n.\n"
    ))
    assert "for n in [1, 2, 3]:" in py


class TestExec:
  def test_let_return_runs(self):
    out = _wrap_and_exec("Let x = 42.\nReturn x.\n", {})
    assert out == 42

  def test_chip_call_runs(self):
    registry = {"add": lambda a, b: a + b}
    out = _wrap_and_exec(
      "Let r = Call [[add]] with a=3, b=4.\nReturn r.\n", registry
    )
    assert out == 7

  def test_shorthand_call_runs(self):
    captured = []
    registry = {"capture": lambda x: captured.append(x)}
    _wrap_and_exec(
      "[[capture]] 42.\nReturn.\n", registry
    )
    assert captured == [42]

  def test_nested_call_runs(self):
    registry = {
      "double": lambda x: x * 2,
      "make_5": lambda: 5,
    }
    out = _wrap_and_exec(
      "Let r = Call [[double]] with x=[[make_5]].\nReturn r.\n", registry
    )
    assert out == 10

  def test_spike_note_runs(self):
    """End-to-end: the spike note's E-- transpiles to runnable Python that
    produces a music21 Part with the right structure."""
    from forge.music.lib import kick, play_at_beats, show_score
    from music21 import stream
    registry = {
      "kick": kick,
      "play_at_beats": play_at_beats,
      "show_score": show_score,
    }
    out = _wrap_and_exec(
      "Let part = Call [[play_at_beats]] with instrument=[[kick]], beats=[1, 3].\n"
      "[[show_score]] part.\n"
      "Return part.\n",
      registry,
    )
    assert isinstance(out, stream.Part)
    notes = list(out.recurse().notes)
    assert len(notes) == 2


class TestUnreachableAfterReturn:
  """Drain 2026-08-23-2000 (c) — statements after a terminal `Return`.

  Driver live repro 2026-08-23 19:41: /generate emitted a duplicated
  `Return result.` and the transpiler passed BOTH through, producing
  dead Python. Adjudicated: strip-with-notice. Rationale in the drain
  FEEDBACK; the short form is that a second Return is LLM noise, not
  authored intent, and turning it into a parse error would convert
  generation sloppiness into a user-facing failure on a note the user
  never typed.
  """

  def test_duplicate_return_emits_one_return(self):
    # The driver's exact shape.
    src = (
      "Let rand = Call [[random]] with.\n"
      "Let result = rand * scale.\n"
      "Return result.\n"
      "Return result.\n"
    )
    py = transpile(parse(src))
    assert py.count("return result") == 1, py

  def test_statements_after_return_are_dropped(self):
    py = transpile(parse("Return 1.\nLet x = 2.\n"))
    assert "return 1" in py
    assert "x = 2" not in py, py

  def test_dropping_unreachable_warns(self):
    import warnings as _w
    with _w.catch_warnings(record=True) as caught:
      _w.simplefilter("always")
      transpile(parse("Return 1.\nReturn 2.\n"))
    msgs = [str(c.message) for c in caught]
    assert any("unreachable" in m for m in msgs), msgs

  def test_unreachable_inside_if_body_is_dropped(self):
    src = (
      "If 1 > 0:\n"
      "  Return 1.\n"
      "  Let dead = 2.\n"
      "Return 0.\n"
    )
    py = transpile(parse(src))
    assert "dead" not in py, py
    assert "return 0" in py

  def test_reachable_code_after_a_nested_return_is_kept(self):
    # NON-VACUITY: the strip must be terminal-only. A Return inside an
    # If body does not make the rest of the enclosing block dead.
    src = (
      "If 1 > 0:\n"
      "  Return 1.\n"
      "Let after = 2.\n"
      "Return after.\n"
    )
    py = transpile(parse(src))
    assert "after = 2" in py, py
    assert "return after" in py, py

  def test_no_warning_when_nothing_is_unreachable(self):
    # NON-VACUITY: the notice must not fire on ordinary recipes.
    import warnings as _w
    with _w.catch_warnings(record=True) as caught:
      _w.simplefilter("always")
      transpile(parse("Let x = 1.\nReturn x.\n"))
    msgs = [str(c.message) for c in caught]
    assert not any("unreachable" in m for m in msgs), msgs
