"""Unit tests for V2 `{{...}}` slot support.

Covers the Phase 1 surface:
- Lexer: `{{free text}}` → SLOT token; empty / nested / unterminated → ParseError
- Parser: SLOT token → SlotExpr AST node in expression position
- Transpiler: SlotExpr renders via the optional `resolve_slot` callable,
  or to a placeholder when no resolver is provided; optional
  `collect_slots` list captures every slot encountered

Phase 2 (executor-side resolve_slot wiring + LLM round-trip + cache) is a
separate drain; this test file locks in the engine-side AST + transpile
contract that wiring will plug into.
"""

import pytest

from forge.e_minus_minus_v2 import parser as p
from forge.e_minus_minus_v2 import transpiler as t


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

def test_lexer_recognizes_slot():
  toks = p._tokenize("{{octopus fact}}")
  toks = [tok for tok in toks if tok.kind != "EOF"]
  assert len(toks) == 1
  assert toks[0].kind == "SLOT"
  assert toks[0].value == "octopus fact"


def test_lexer_strips_surrounding_whitespace_in_slot():
  toks = p._tokenize("{{  some thing  }}")
  toks = [tok for tok in toks if tok.kind != "EOF"]
  assert toks[0].kind == "SLOT"
  assert toks[0].value == "some thing"


def test_lexer_slot_inline_with_other_tokens():
  toks = p._tokenize("Let x = {{a fact}}.")
  kinds = [(tok.kind, tok.value) for tok in toks if tok.kind != "EOF"]
  assert kinds == [
    ("KEYWORD", "Let"),
    ("IDENT", "x"),
    ("OP", "="),
    ("SLOT", "a fact"),
    ("OP", "."),
  ]


def test_lexer_empty_slot_is_parse_error():
  with pytest.raises(p.ParseError, match="empty slot"):
    p._tokenize("{{}}")


def test_lexer_nested_slot_is_parse_error():
  with pytest.raises(p.ParseError, match="nested slot"):
    p._tokenize("{{outer {{ inner }} more}}")


def test_lexer_unterminated_slot_is_parse_error():
  with pytest.raises(p.ParseError, match="unterminated slot"):
    p._tokenize("{{ no close")


def test_lexer_newline_in_slot_is_parse_error():
  with pytest.raises(p.ParseError, match="unterminated slot"):
    p._tokenize("{{ multi\nline }}")


# ---------------------------------------------------------------------------
# Parser — SlotExpr in expression positions
# ---------------------------------------------------------------------------

def test_parser_slot_in_let_rhs():
  mod = p.parse("Let fact = {{octopus fact}}.\nReturn fact.")
  assert isinstance(mod.statements[0], p.LetStmt)
  assert isinstance(mod.statements[0].value, p.SlotExpr)
  assert mod.statements[0].value.text == "octopus fact"


def test_parser_slot_in_return():
  mod = p.parse("Return {{the answer}}.")
  assert isinstance(mod.statements[0], p.ReturnStmt)
  assert isinstance(mod.statements[0].value, p.SlotExpr)
  assert mod.statements[0].value.text == "the answer"


def test_parser_slot_inside_chip_call_kwarg():
  # V2 has no top-level `Call ... .` statement; chip calls live in
  # expression position (Let RHS, Return value, kwarg). This test puts
  # a SlotExpr in a kwarg of a chip call on the Return.
  mod = p.parse(
    'Return Call [[print]] with text={{a 5-word haiku title}}.'
  )
  ret = mod.statements[0]
  assert isinstance(ret, p.ReturnStmt)
  chip = ret.value
  assert isinstance(chip, p.ChipCall)
  assert chip.name == "print"
  assert len(chip.kwargs) == 1
  slot = chip.kwargs[0].value
  assert isinstance(slot, p.SlotExpr)
  assert slot.text == "a 5-word haiku title"


def test_parser_slot_in_arithmetic():
  mod = p.parse("Let count = {{guitar strings}} + 1.\nReturn count.")
  let = mod.statements[0]
  assert isinstance(let, p.LetStmt)
  assert isinstance(let.value, p.BinaryOp)
  assert isinstance(let.value.left, p.SlotExpr)
  assert let.value.left.text == "guitar strings"


# ---------------------------------------------------------------------------
# Transpiler — three modes (no resolver, resolver, collector)
# ---------------------------------------------------------------------------

def test_transpile_slot_without_resolver_emits_placeholder():
  mod = p.parse("Let x = {{octopus fact}}.\nReturn x.")
  out = t.transpile(mod)
  # Placeholder is a string literal so the snippet still executes;
  # the cohort sees a clearly-marked "unresolved slot: ..." text.
  assert "'<unresolved slot: octopus fact>'" in out
  assert "return x" in out


def test_transpile_slot_with_resolver_substitutes_python_expr():
  mod = p.parse("Let n = {{guitar strings}}.\nReturn n.")
  out = t.transpile(mod, resolve_slot=lambda text: "6")
  assert "n = 6" in out
  assert "return n" in out


def test_transpile_slot_with_resolver_for_string_literal():
  mod = p.parse("Let g = {{a hello}}.\nReturn g.")
  out = t.transpile(mod, resolve_slot=lambda text: repr("hello"))
  assert "g = 'hello'" in out


def test_transpile_collect_slots_inventory():
  mod = p.parse(
    "Let a = {{first}}.\nLet b = {{second}}.\nReturn a."
  )
  collected = []
  t.transpile(
    mod,
    resolve_slot=lambda text: f'"<{text}>"',
    collect_slots=collected,
  )
  texts = [text for text, _ in collected]
  assert texts == ["first", "second"]
  # The collector pairs slot text with the rendered Python expression.
  assert collected[0][1] == '"<first>"'


def test_transpile_collect_slots_without_resolver_collects_placeholders():
  mod = p.parse("Let a = {{x}}.\nReturn a.")
  collected = []
  t.transpile(mod, collect_slots=collected)
  assert len(collected) == 1
  assert collected[0][0] == "x"
  assert "unresolved slot" in collected[0][1]


def test_transpile_state_cleared_between_calls():
  """After a transpile call returns, the module-state resolver +
  collector must be cleared so subsequent calls without those args
  see no resolver."""
  mod1 = p.parse("Let x = {{first}}.\nReturn x.")
  t.transpile(mod1, resolve_slot=lambda text: "1")
  # Second call with no resolver should emit placeholder, not "1".
  mod2 = p.parse("Let y = {{second}}.\nReturn y.")
  out = t.transpile(mod2)
  assert "'<unresolved slot: second>'" in out


# ---------------------------------------------------------------------------
# Regression: non-slot transpile paths unchanged
# ---------------------------------------------------------------------------

def test_existing_non_slot_transpile_still_works():
  """V2 module without any SlotExpr should transpile identically to
  pre-Phase-1 output."""
  mod = p.parse(
    "Let x = Call [[temperature_to_speed]] with temperature=\"high\".\nReturn x."
  )
  out = t.transpile(mod)
  assert "x = temperature_to_speed(temperature='high')" in out
  assert "return x" in out
  assert "unresolved" not in out
