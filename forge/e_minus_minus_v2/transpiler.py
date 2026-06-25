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
    CallStmt,
    ChipCall,
    ForEachStmt,
    IdentRef,
    Kwarg,
    LetStmt,
    ListLit,
    Module,
    NumberLit,
    RepeatStmt,
    ReturnStmt,
    StringLit,
)


INDENT = "  "


def transpile(module: Module) -> str:
  """Render a Module as Python source wrapped in `def compute(context):`."""
  body_lines = _render_block(module.statements, depth=1)
  if not body_lines:
    body_lines = [INDENT + "pass"]
  return "def compute(context):\n" + "\n".join(body_lines) + "\n"


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
  raise TypeError(f"unknown expression type: {type(expr).__name__}")
