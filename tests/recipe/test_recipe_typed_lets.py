"""Drain 2026-08-10-1610 — Approach C: optional type annotations on Let.

Grammar: `Let X: Type = expr.` — the annotation is opaque text between
`:` and `=` (primitives, dotted names, generics, enum literals with
`|`). `Let X: T = required.` declares a caller-must-pass input (the
`required` sentinel is only special when a type annotation is
present; untyped `Let X = required.` keeps its old IdentRef meaning).

Leading typed Lets whose value is a LITERAL (or `required`) are INPUT
DECLARATIONS: transpile lifts them into the compute() signature
(annotation + default; required params first) and omits them from the
body. Typed Lets elsewhere (or with non-literal values) stay local
assignments. `derive_inputs_from_recipe` exposes the declarations for
frontmatter derivation / MCP surfaces.
"""

from forge.recipe import parse, transpile
from forge.recipe.parser import LetStmt, derive_inputs_from_recipe


# ---- parsing ----------------------------------------------------------

def test_parse_untyped_let():
  mod = parse("Let X = 42.\nReturn X.")
  let = mod.statements[0]
  assert isinstance(let, LetStmt)
  assert let.type_hint is None
  assert let.is_required_input is False


def test_parse_typed_let_primitive():
  mod = parse("Let X: int = 42.\nReturn X.")
  assert mod.statements[0].type_hint == "int"


def test_parse_typed_let_generic():
  mod = parse("Let X: list[str] = [].\nReturn X.")
  assert mod.statements[0].type_hint == "list[str]"


def test_parse_typed_let_dotted_name():
  mod = parse('Let s: music21.Stream = required.\nReturn s.')
  assert mod.statements[0].type_hint == "music21.Stream"
  assert mod.statements[0].is_required_input is True


def test_parse_typed_let_enum_literal():
  mod = parse("Let X: 'major' | 'minor' = \"major\".\nReturn X.")
  assert mod.statements[0].type_hint == "'major' | 'minor'"


def test_parse_typed_let_required_sentinel():
  mod = parse("Let X: int = required.\nReturn X.")
  let = mod.statements[0]
  assert let.is_required_input is True
  assert let.type_hint == "int"


def test_untyped_required_keeps_identref_meaning():
  mod = parse("Let X = required.\nReturn X.")
  let = mod.statements[0]
  assert let.is_required_input is False
  assert let.type_hint is None


# ---- transpile --------------------------------------------------------

def test_transpile_typed_input_to_signature():
  py = transpile(parse('Let name: str = "world".\nReturn name.'))
  assert "def compute(context, name: str = 'world'):" in py
  # Lifted into the signature — no duplicate body assignment.
  assert "name = 'world'" not in py
  assert "return name" in py


def test_transpile_required_input_to_signature():
  py = transpile(parse("Let n: int = required.\nReturn n."))
  assert "def compute(context, n: int):" in py


def test_transpile_required_params_precede_defaulted():
  py = transpile(parse(
    'Let a: str = "x".\nLet b: int = required.\nReturn b.'))
  assert "def compute(context, b: int, a: str = 'x'):" in py


def test_transpile_typed_let_with_nonliteral_value_stays_local():
  py = transpile(parse(
    "Let items: list[str] = [].\nLet n: int = 1 + 1.\nReturn n."))
  assert "def compute(context, items: list[str] = []):" in py
  # The chip-call Let is NOT an input — stays in the body.
  assert "n = " in py


def test_transpile_regression_untyped_lets_unchanged():
  before = transpile(parse("Let X = 42.\nReturn X."))
  assert "def compute(context):" in before
  assert "X = 42" in before


def test_transpile_typed_merges_with_inputs_param_typed_wins():
  from forge.recipe import InputDecl
  decls = [
    InputDecl(name="bars", default=4, has_default=True, doc=""),
    InputDecl(name="mode", default="major", has_default=True, doc=""),
  ]
  py = transpile(
    parse('Let bars: int = 8.\nReturn bars.'), inputs=decls)
  # Typed Let overrides the ## Inputs decl for the same name; the
  # non-colliding ## Inputs decl survives.
  assert "bars: int = 8" in py
  assert "mode='major'" in py
  assert py.count("bars") >= 2  # signature + body use


# ---- derivation -------------------------------------------------------

def test_frontmatter_inputs_derived_from_typed_lets():
  decls = derive_inputs_from_recipe(
    'Let pitches: list[str] = ["C4"].\n'
    "Let tempo: int = required.\n"
    "Let x = 1 + tempo.\n"
    "Return x.")
  assert [d.name for d in decls] == ["pitches", "tempo"]
  assert decls[0].type_hint == "list[str]"
  assert decls[0].default == ["C4"]
  assert decls[0].has_default is True
  assert decls[1].has_default is False


def test_derivation_stops_at_first_non_input_statement():
  decls = derive_inputs_from_recipe(
    "Let a: int = 1.\nLet b = 1 + 1.\nLet c: int = 2.\nReturn c.")
  # c is typed but appears after a non-input statement — not an input.
  assert [d.name for d in decls] == ["a"]


# ---- migration case-study (rhythmic_line) -----------------------------

RHYTHMIC_LINE_TYPED = (
  'Let pitches: list[str] = ["C4", "D4", "E4", "F4"].\n'
  'Let rhythm_pattern: list[str] = ["Q", "Q", "E", "E"].\n'
  'Let valid_codes = ["W", "H", "Q", "E", "S"].\n'
  'Let line = {{ [{"pitch": p, "duration": d} for p, d in zip(pitches, rhythm_pattern)] }}.\n'
  "Return line.")


def test_migration_case_study_rhythmic_line():
  decls = derive_inputs_from_recipe(RHYTHMIC_LINE_TYPED)
  assert [d.name for d in decls] == ["pitches", "rhythm_pattern"]
  py = transpile(parse(RHYTHMIC_LINE_TYPED), resolve_slot=lambda t: t)
  assert ("def compute(context, pitches: list[str] = ['C4', 'D4', 'E4', 'F4'], "
          "rhythm_pattern: list[str] = ['Q', 'Q', 'E', 'E']):") in py
  scope = {}
  exec(py, scope)
  out = scope["compute"](context=None, pitches=["C4"], rhythm_pattern=["Q"])
  assert out == [{"pitch": "C4", "duration": "Q"}]
