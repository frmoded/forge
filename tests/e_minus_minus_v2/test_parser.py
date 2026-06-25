"""V2 E-- parser tests — verify each spec §5 construct yields the expected AST."""

import pytest
from forge.e_minus_minus_v2 import parse
from forge.e_minus_minus_v2.parser import (
    CallStmt,
    ChipCall,
    ForEachStmt,
    IdentRef,
    LetStmt,
    ListLit,
    NumberLit,
    ParseError,
    RepeatStmt,
    ReturnStmt,
    StringLit,
)


class TestLet:
  def test_let_number(self):
    m = parse("Let x = 1.")
    assert len(m.statements) == 1
    s = m.statements[0]
    assert isinstance(s, LetStmt)
    assert s.name == "x"
    assert isinstance(s.value, NumberLit)
    assert s.value.value == 1

  def test_let_string(self):
    m = parse('Let greeting = "hello".')
    s = m.statements[0]
    assert isinstance(s.value, StringLit)
    assert s.value.value == "hello"

  def test_let_list(self):
    m = parse("Let beats = [1, 3].")
    s = m.statements[0]
    assert isinstance(s.value, ListLit)
    assert len(s.value.items) == 2
    assert s.value.items[0].value == 1
    assert s.value.items[1].value == 3

  def test_let_empty_list(self):
    m = parse("Let xs = [].")
    s = m.statements[0]
    assert isinstance(s.value, ListLit)
    assert s.value.items == []

  def test_let_bare_wikilink(self):
    m = parse("Let drum = [[kick]].")
    s = m.statements[0]
    assert isinstance(s.value, ChipCall)
    assert s.value.name == "kick"
    assert s.value.kwargs == []

  def test_let_call_with_kwargs(self):
    m = parse(
      "Let part = Call [[play_at_beats]] with instrument=[[kick]], beats=[1, 3]."
    )
    s = m.statements[0]
    assert isinstance(s.value, ChipCall)
    assert s.value.name == "play_at_beats"
    assert len(s.value.kwargs) == 2
    assert s.value.kwargs[0].name == "instrument"
    assert isinstance(s.value.kwargs[0].value, ChipCall)
    assert s.value.kwargs[0].value.name == "kick"
    assert s.value.kwargs[1].name == "beats"
    assert isinstance(s.value.kwargs[1].value, ListLit)


class TestReturn:
  def test_return_value(self):
    m = parse("Return x.")
    s = m.statements[0]
    assert isinstance(s, ReturnStmt)
    assert isinstance(s.value, IdentRef)
    assert s.value.name == "x"

  def test_return_bare(self):
    m = parse("Return.")
    s = m.statements[0]
    assert isinstance(s, ReturnStmt)
    assert s.value is None


class TestShorthandCall:
  def test_call_with_arg(self):
    m = parse("[[show_score]] part.")
    s = m.statements[0]
    assert isinstance(s, CallStmt)
    assert s.name == "show_score"
    assert isinstance(s.arg, IdentRef)
    assert s.arg.name == "part"

  def test_call_no_arg(self):
    m = parse("[[reset]].")
    s = m.statements[0]
    assert isinstance(s, CallStmt)
    assert s.name == "reset"
    assert s.arg is None


class TestRepeat:
  def test_repeat_block(self):
    m = parse(
      "Repeat 3 times:\n"
      "  Let x = 1.\n"
      "Return x.\n"
    )
    assert len(m.statements) == 2
    repeat = m.statements[0]
    assert isinstance(repeat, RepeatStmt)
    assert repeat.count.value == 3
    assert len(repeat.body) == 1
    assert isinstance(repeat.body[0], LetStmt)
    # Statement after the block is at indent 0.
    assert isinstance(m.statements[1], ReturnStmt)


class TestForEach:
  def test_foreach_block(self):
    m = parse(
      "For each n in [1, 2, 3]:\n"
      "  Let y = n.\n"
      "Return y.\n"
    )
    assert len(m.statements) == 2
    foreach = m.statements[0]
    assert isinstance(foreach, ForEachStmt)
    assert foreach.var == "n"
    assert isinstance(foreach.iterable, ListLit)
    assert len(foreach.body) == 1


class TestSpikeNote:
  """End-to-end parse of the spike note's E--."""

  def test_spike_note_parses(self):
    emm = (
      "Let part = Call [[play_at_beats]] with instrument=[[kick]], beats=[1, 3].\n"
      "[[show_score]] part.\n"
      "Return part.\n"
    )
    m = parse(emm)
    assert len(m.statements) == 3
    assert isinstance(m.statements[0], LetStmt)
    assert isinstance(m.statements[1], CallStmt)
    assert isinstance(m.statements[2], ReturnStmt)


class TestErrors:
  def test_let_missing_equals(self):
    with pytest.raises(ParseError):
      parse("Let x 1.")

  def test_unclosed_wikilink(self):
    with pytest.raises(ParseError):
      parse("Let x = [[unclosed.")

  def test_unrecognized_statement(self):
    with pytest.raises(ParseError):
      parse("Frobnicate 5.")
