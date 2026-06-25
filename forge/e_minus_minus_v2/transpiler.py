"""V2 E-- transpiler — AST → Python source.

Wraps every program in `def compute(context):` per the Forge snippet
convention. Chip-call `[[name]]` compiles to a direct Python function
call `name(...)` — the executor injects engine primitives + sibling-
snippet shims as named globals (`_FORGE_MUSIC_LIB_NAMES`,
`_build_snippet_shims`) so `kick()`, `play_at_beats(...)`,
`show_score(...)` etc. resolve at runtime through the same mechanism
the V1 snippets used.

Indentation: 2 spaces per level (matches Forge codebase style).
"""

from .parser import (
    BinaryOp,
    BoolLit,
    CallStmt,
    ChipCall,
    ForEachStmt,
    IdentRef,
    IfStmt,
    Kwarg,
    LetStmt,
    ListLit,
    Module,
    NoneLit,
    NumberLit,
    RepeatStmt,
    ReturnStmt,
    StringLit,
)


INDENT = "  "


def transpile(module: Module, inputs=None) -> str:
  """Render a Module as Python source wrapped in `def compute(context, ...):`.

  Args:
    module: V2 AST.
    inputs: optional list of InputDecl from extract_inputs_declarations.
      When provided, each input becomes a kwarg on the compute signature
      (with its declared default). The V1 executor passes inputs as
      kwargs in the same way, so V2 reuses V1's calling convention.
  """
  if inputs:
    kwargs = ", ".join(
      f"{d.name}={_render_default(d.default)}" if d.has_default else d.name
      for d in inputs
    )
    sig = f"def compute(context, {kwargs}):"
  else:
    sig = "def compute(context):"
  body_lines = _render_block(module.statements, depth=1)
  if not body_lines:
    body_lines = [INDENT + "pass"]
  return sig + "\n" + "\n".join(body_lines) + "\n"


def _render_default(v):
  """repr() works for ints, floats, strings, bools, None, lists of literals."""
  return repr(v)


def _render_block(stmts, depth):
  out = []
  for s in stmts:
    out.extend(_render_stmt(s, depth))
  return out


def _render_stmt(stmt, depth):
  pad = INDENT * depth
  if isinstance(stmt, LetStmt):
    return [f"{pad}{stmt.name} = {_render_expr(stmt.value)}"]
  if isinstance(stmt, ReturnStmt):
    if stmt.value is None:
      return [f"{pad}return None"]
    return [f"{pad}return {_render_expr(stmt.value)}"]
  if isinstance(stmt, CallStmt):
    if stmt.arg is None:
      return [f"{pad}{stmt.name}()"]
    return [f"{pad}{stmt.name}({_render_expr(stmt.arg)})"]
  if isinstance(stmt, RepeatStmt):
    inner = _render_block(stmt.body, depth + 1)
    if not inner:
      inner = [INDENT * (depth + 1) + "pass"]
    return [
      f"{pad}for _ in range({_render_expr(stmt.count)}):",
      *inner,
    ]
  if isinstance(stmt, ForEachStmt):
    inner = _render_block(stmt.body, depth + 1)
    if not inner:
      inner = [INDENT * (depth + 1) + "pass"]
    return [
      f"{pad}for {stmt.var} in {_render_expr(stmt.iterable)}:",
      *inner,
    ]
  if isinstance(stmt, IfStmt):
    then_inner = _render_block(stmt.then_body, depth + 1)
    if not then_inner:
      then_inner = [INDENT * (depth + 1) + "pass"]
    out = [f"{pad}if {_render_expr(stmt.condition)}:", *then_inner]
    if stmt.else_body:
      else_inner = _render_block(stmt.else_body, depth + 1)
      out.append(f"{pad}else:")
      out.extend(else_inner)
    return out
  raise TypeError(f"unknown statement type: {type(stmt).__name__}")


def _render_expr(expr) -> str:
  if isinstance(expr, ChipCall):
    if not expr.kwargs:
      return f"{expr.name}()"
    kw = ", ".join(
      f"{k.name}={_render_expr(k.value)}" for k in expr.kwargs
    )
    return f"{expr.name}({kw})"
  if isinstance(expr, ListLit):
    return "[" + ", ".join(_render_expr(it) for it in expr.items) + "]"
  if isinstance(expr, NumberLit):
    return repr(expr.value)
  if isinstance(expr, StringLit):
    return repr(expr.value)
  if isinstance(expr, IdentRef):
    return expr.name
  if isinstance(expr, BoolLit):
    return "True" if expr.value else "False"
  if isinstance(expr, NoneLit):
    return "None"
  if isinstance(expr, BinaryOp):
    return f"({_render_expr(expr.left)} {expr.op} {_render_expr(expr.right)})"
  raise TypeError(f"unknown expression type: {type(expr).__name__}")
