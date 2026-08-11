"""Drain 2026-08-10-2000 — dedicated `Input` keyword for parameters.

Retires the drain-1610 positional-typed-Let-as-parameter inference in
favor of an explicit statement: `Input NAME: TYPE (= DEFAULT)?.` — no
default means required. Legacy typed-Let-at-top (drain 1610 style)
still PARSES for backward compat, and — when a Recipe has NO Input
statements at all — still PROMOTES to the signature via the old
leading-run inference (with a deprecation warning); once even one
Input statement is present, Input decls are the ONLY signature
source and typed Lets (anywhere) render as annotated locals instead
(the drain-1610 "WAT": annotations on non-promoted typed Lets used to
be silently dropped; fixed here for both modes).

Also: enum-literal type hints (`'A' | 'B'`) transpile to Python
`Literal["A", "B"]` with an injected `from typing import Literal`.
"""

import warnings

from forge.recipe import parse, transpile
from forge.recipe.parser import InputStmt, LetStmt


# ---- parsing ------------------------------------------------------------

def test_parse_input_with_default():
  mod = parse("Input X: int = 42.\nReturn X.")
  stmt = mod.statements[0]
  assert isinstance(stmt, InputStmt)
  assert stmt.name == "X"
  assert stmt.type_hint == "int"
  assert stmt.is_required is False
  assert stmt.default == 42


def test_parse_input_no_default_required():
  mod = parse("Input X: int.\nReturn X.")
  stmt = mod.statements[0]
  assert stmt.is_required is True
  assert stmt.default is None
  assert stmt.type_hint == "int"


def test_parse_input_enum_literal_type():
  mod = parse('Input mode: \'major\' | \'minor\' = "major".\nReturn mode.')
  assert mod.statements[0].type_hint == "'major' | 'minor'"


def test_parse_input_generic_type():
  mod = parse("Input xs: list[str] = [].\nReturn xs.")
  assert mod.statements[0].type_hint == "list[str]"


def test_parse_input_dotted_type_required():
  mod = parse("Input stream: music21.Stream.\nReturn stream.")
  assert mod.statements[0].type_hint == "music21.Stream"
  assert mod.statements[0].is_required is True


def test_parse_legacy_typed_let_still_parses():
  # Backward compat: the syntax itself must not become a ParseError.
  mod = parse("Let X: int = 42.\nReturn X.")
  let = mod.statements[0]
  assert isinstance(let, LetStmt)
  assert let.type_hint == "int"


# ---- transpile: Input mode ----------------------------------------------

def test_transpile_input_to_signature():
  py = transpile(parse("Input X: int = 42.\nReturn X."))
  assert "def compute(context, X: int = 42):" in py
  assert "return X" in py


def test_transpile_input_required_to_signature():
  py = transpile(parse("Input X: int.\nReturn X."))
  assert "def compute(context, X: int):" in py


def test_transpile_input_required_before_defaulted():
  py = transpile(parse(
    'Input a: str = "x".\nInput b: int.\nReturn b.'))
  assert "def compute(context, b: int, a: str = 'x'):" in py


def test_transpile_enum_literal_becomes_python_literal():
  py = transpile(parse(
    'Input mode: \'major\' | \'minor\' = "major".\nReturn mode.'))
  assert "from typing import Literal" in py
  assert "mode: Literal['major', 'minor'] = 'major'" in py


def test_transpile_no_literal_import_when_no_enum_type():
  py = transpile(parse("Input n: int = 1.\nReturn n."))
  assert "from typing import Literal" not in py


def test_transpile_typed_local_annotation_preserved_in_input_mode():
  # Once Input is present, typed Lets anywhere are ordinary ANNOTATED
  # locals — the drain-1610 WAT (silently dropping the annotation) is
  # fixed here.
  py = transpile(parse(
    "Input n: int = 1.\nLet doubled: int = n + n.\nReturn doubled."))
  assert "def compute(context, n: int = 1):" in py
  assert "doubled: int = (n + n)" in py


def test_input_statement_omitted_from_body():
  py = transpile(parse("Input n: int = 1.\nReturn n."))
  # No stray body line for the Input declaration itself.
  lines = [l.strip() for l in py.splitlines()]
  assert not any(l.startswith("n =") or l.startswith("n:") for l in lines[1:-1])


# ---- transpile: legacy fallback (no Input statements) --------------------

def test_transpile_legacy_typed_let_still_promotes_with_warning():
  with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    py = transpile(parse("Let X: int = 42.\nReturn X."))
  assert "def compute(context, X: int = 42):" in py
  assert any(issubclass(w.category, DeprecationWarning) for w in caught)
  assert any("Input" in str(w.message) for w in caught)


def test_transpile_legacy_untyped_lets_no_warning_no_change():
  with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    py = transpile(parse("Let X = 42.\nReturn X."))
  assert "def compute(context):" in py
  assert "X = 42" in py
  assert not any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_transpile_legacy_non_leading_typed_let_annotation_preserved():
  # Non-promoted typed Let (not in the leading run) — annotation kept,
  # not silently dropped, even in legacy mode.
  py = transpile(parse(
    "Let a = 1.\nLet b: int = a + 1.\nReturn b."))
  assert "def compute(context):" in py
  assert "b: int = (a + 1)" in py


# ---- migration case-study (pitched_line) ---------------------------------

PITCHED_LINE_INPUT_KEYWORD = (
  'Input pitches: list[str] = ["C4", "D4", "E4", "F4"].\n'
  'Input rhythm_pattern: list[str] = ["Q", "Q", "E", "E"].\n'
  'Let valid_codes = ["W", "H", "Q", "E", "S"].\n'
  'Let line = {{ [{"pitch": p, "duration": d} for p, d in zip(pitches, rhythm_pattern)] }}.\n'
  "Return line.")


def test_pitched_line_migrated_transpile():
  py = transpile(parse(PITCHED_LINE_INPUT_KEYWORD), resolve_slot=lambda t: t)
  assert ("def compute(context, pitches: list[str] = ['C4', 'D4', 'E4', 'F4'], "
          "rhythm_pattern: list[str] = ['Q', 'Q', 'E', 'E']):") in py
  scope = {}
  exec(py, scope)
  out = scope["compute"](context=None, pitches=["C4"], rhythm_pattern=["Q"])
  assert out == [{"pitch": "C4", "duration": "Q"}]
