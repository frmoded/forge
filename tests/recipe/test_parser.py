"""V2 E-- parser tests — verify each spec §5 construct yields the expected AST."""

import pytest
from forge.recipe import parse
from forge.recipe.parser import (
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


# ---------------------------------------------------------------------------
# Drain 2026-07-14-1235 — ParseError structured lineno/col_offset.
#
# Pre-drain, every raise site embedded location in the message string
# ("unexpected char '=' at line 3, col 12") and `.lineno` was None.
# Downstream consumers (forge-transpile's /compile → ParseErrorDetail,
# plugin's Recipe error UI) had to regex-parse the message. Post-drain
# every raise site with a token in scope sets `.lineno` + `.col_offset`
# structurally and drops the "at line X, col Y" tail from the message.
# ---------------------------------------------------------------------------


class TestParseErrorLocation:
  def test_parse_error_sets_lineno_on_unexpected_token(self):
    """Drain §5 test #1 — syntax error on line 3 sets `.lineno == 3`."""
    src = "Let a = 1.\nLet b = 2.\nLet bad === 5.\nReturn a.\n"
    with pytest.raises(ParseError) as exc_info:
      parse(src)
    assert exc_info.value.lineno == 3

  def test_parse_error_sets_col_offset_when_available(self):
    """Drain §5 test #2 — col_offset carries the offending token's
    column. `Let bad === 5.` — the parser trips on the second `=` after
    consuming `Let bad =`, so column should be >= 1 (parser tokens are
    1-indexed)."""
    src = "Let bad === 5.\n"
    with pytest.raises(ParseError) as exc_info:
      parse(src)
    assert exc_info.value.col_offset is not None
    assert exc_info.value.col_offset >= 1
    # SyntaxError-standard .offset mirrors .col_offset (both are set).
    assert exc_info.value.offset == exc_info.value.col_offset

  def test_parse_error_message_does_not_embed_location(self):
    """Drain §5 test #3 — when structured fields are set, the message
    text no longer duplicates "at line X, col Y" / "on line X"."""
    src = "Let x === 5.\n"
    with pytest.raises(ParseError) as exc_info:
      parse(src)
    msg = str(exc_info.value)
    assert "at line" not in msg
    assert "on line" not in msg
    # But the original substantive content is preserved — this is a
    # tokenizer-level "unexpected char" for the extra `=`.
    assert "unexpected char" in msg or "expected" in msg

  def test_parse_error_lineno_None_when_context_unknown(self):
    """Drain §5 test #4 — raise sites that legitimately can't derive
    location (empty expression called with no tokens in hand) leave
    `.lineno` as None (not 0). Per drain §Don'ts: use Python's None
    convention, not a "location unknown" sentinel."""
    from forge.recipe.parser import _parse_expr

    with pytest.raises(ParseError) as exc_info:
      _parse_expr([])
    assert exc_info.value.lineno is None
    assert exc_info.value.col_offset is None

  def test_parse_error_lineno_on_tokenizer_error(self):
    """Regression — tokenizer-level errors (unexpected char, unterminated
    string, malformed slot) also set structured location. Pre-drain these
    used f"at line {line}, col {col}" in the message."""
    with pytest.raises(ParseError) as exc_info:
      parse("Let x = @.\n")
    assert exc_info.value.lineno == 1
    assert exc_info.value.col_offset is not None


# -- CW-e-minus-lexer-hash-in-string-literal-parse-bug (drain 2026-07-24-1735) --


class TestCommentsAndHashInStrings:
  """The drain motivated by wizard's `"F#"` report. Investigation found
  cases 1+2 (# INSIDE strings) already worked; cases 4+5 (# as line
  comment) never worked — the tokenizer had no `#` handler at all.
  This drain adds comment support to close cases 4+5 while preserving
  the existing string-literal-with-# behavior."""

  def test_string_with_hash_at_end(self):
    """Case 1 — `"F#"` literal must lex as the 2-char sharp-pitch string."""
    m = parse('Return "F#".')
    assert len(m.statements) == 1
    s = m.statements[0]
    assert isinstance(s, ReturnStmt)
    assert isinstance(s.value, StringLit)
    assert s.value.value == "F#"

  def test_string_with_hash_in_middle(self):
    """Case 3 — `#` embedded mid-string must be preserved verbatim."""
    m = parse('Return "before # after".')
    s = m.statements[0]
    assert isinstance(s.value, StringLit)
    assert s.value.value == "before # after"

  def test_string_with_hash_as_chip_kwarg(self):
    """Case 2 — sharp pitch names as chip kwarg values (the real wizard
    reproduction: `Call [[diatonic_scale]] with tonic="F#"`)."""
    m = parse('Return Call [[diatonic_scale]] with tonic="F#".')
    s = m.statements[0]
    assert isinstance(s, ReturnStmt)
    call = s.value
    assert isinstance(call, ChipCall)
    assert call.name == "diatonic_scale"
    assert call.kwargs[0].name == "tonic"
    assert isinstance(call.kwargs[0].value, StringLit)
    assert call.kwargs[0].value.value == "F#"

  def test_hash_line_comment_alone(self):
    """Case 4 — bare `#` line comment on its own must be stripped, and
    surrounding statements parse cleanly."""
    m = parse('Let x = 1. # this is a comment\nReturn x.')
    assert len(m.statements) == 2
    assert isinstance(m.statements[0], LetStmt)
    assert m.statements[0].name == "x"
    assert isinstance(m.statements[1], ReturnStmt)

  def test_hash_line_comment_after_string_literal(self):
    """Case 5 — a `#` line comment AFTER a string literal must not confuse
    the string handler (this is the exact case where a naive string-in-
    comment-state fix could regress)."""
    m = parse('Let x = "quoted". # tail comment\nReturn x.')
    assert len(m.statements) == 2
    assert isinstance(m.statements[0], LetStmt)
    assert isinstance(m.statements[0].value, StringLit)
    assert m.statements[0].value.value == "quoted"

  def test_full_line_comment(self):
    """A `#`-prefixed full line (with only leading whitespace) is a
    comment and doesn't emit any tokens on that line."""
    m = parse('# top-of-file comment\nReturn 1.')
    assert len(m.statements) == 1
    s = m.statements[0]
    assert isinstance(s, ReturnStmt)
    assert isinstance(s.value, NumberLit)
    assert s.value.value == 1
