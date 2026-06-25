"""V2 `## Inputs` declaration parsing + transpile threading tests."""

from forge.e_minus_minus_v2 import (
    extract_inputs_declarations,
    parse,
    transpile,
)


class TestExtractInputs:
  def test_no_inputs_section(self):
    body = "# Description\n\nNo inputs here.\n"
    assert extract_inputs_declarations(body) == []

  def test_inputs_none_placeholder(self):
    body = "# Description\n\n## Inputs\n\n(none)\n"
    assert extract_inputs_declarations(body) == []

  def test_single_input_with_default(self):
    body = "# Description\n\n## Inputs\n- bars (default 4) — section length\n"
    decls = extract_inputs_declarations(body)
    assert len(decls) == 1
    d = decls[0]
    assert d.name == "bars"
    assert d.default == 4
    assert d.has_default is True
    assert "section length" in d.doc

  def test_string_default(self):
    body = '# Description\n\n## Inputs\n- name (default "world") — greeting target\n'
    decls = extract_inputs_declarations(body)
    assert decls[0].default == "world"

  def test_multiple_inputs(self):
    body = (
      "# Description\n\n## Inputs\n"
      "- a (default 0) — first addend\n"
      "- b (default 0) — second addend\n"
    )
    decls = extract_inputs_declarations(body)
    assert [d.name for d in decls] == ["a", "b"]
    assert [d.default for d in decls] == [0, 0]

  def test_input_without_default(self):
    body = "# Description\n\n## Inputs\n- name — required param\n"
    decls = extract_inputs_declarations(body)
    assert decls[0].name == "name"
    assert decls[0].has_default is False

  def test_inputs_stops_at_next_heading(self):
    body = (
      "# Description\n\n## Inputs\n"
      "- bars (default 4) — section length\n"
      "## Design notes\n"
      "- should NOT parse as input\n"
    )
    decls = extract_inputs_declarations(body)
    assert len(decls) == 1
    assert decls[0].name == "bars"


class TestTranspileWithInputs:
  def test_empty_inputs_no_kwargs(self):
    py = transpile(parse("Return 1."), inputs=None)
    assert "def compute(context):" in py

  def test_input_becomes_kwarg(self):
    from forge.e_minus_minus_v2 import InputDecl
    inputs = [InputDecl(name="bars", default=4, has_default=True, doc="")]
    py = transpile(parse("Return bars."), inputs=inputs)
    assert "def compute(context, bars=4):" in py
    assert "return bars" in py

  def test_input_accessible_in_body_at_exec(self):
    from forge.e_minus_minus_v2 import InputDecl
    inputs = [InputDecl(name="bars", default=4, has_default=True, doc="")]
    py = transpile(parse("Let n = bars.\nReturn n."), inputs=inputs)
    scope = {}
    exec(py, scope)
    # Default fires.
    assert scope["compute"](context=None) == 4
    # Override.
    assert scope["compute"](context=None, bars=10) == 10
