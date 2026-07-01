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
