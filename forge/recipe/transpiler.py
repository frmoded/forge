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

import warnings

from .parser import (
    BinaryOp,
    BoolLit,
    CallStmt,
    ChipCall,
    ExprStmt,
    ForEachStmt,
    IdentRef,
    IfStmt,
    InputStmt,
    Kwarg,
    LetStmt,
    ListLit,
    Module,
    NoneLit,
    NumberLit,
    RepeatStmt,
    ReturnStmt,
    SlotExpr,
    StringLit,
)


INDENT = "  "


# Module-scoped state for the active resolve_slot callable + an unresolved-
# slot collector. transpile() sets/clears these around _render_expr so the
# leaf renderers can reach the resolver without threading it through every
# call. Mirrors V1 vendored E--'s emitter shape (which passes resolve_slot
# through every _emit_expr call directly — V2 picks the module-state pattern
# instead for shorter signatures, since the dialect AST is larger).
_active_resolve_slot = None
_active_slot_collector = None


def transpile(module: Module, inputs=None, resolve_slot=None,
              collect_slots=None) -> str:
  """Render a Module as Python source wrapped in `def compute(context, ...):`.

  Args:
    module: V2 AST.
    inputs: optional list of InputDecl from extract_inputs_declarations.
      When provided, each input becomes a kwarg on the compute signature
      (with its declared default). The V1 executor passes inputs as
      kwargs in the same way, so V2 reuses V1's calling convention.
    resolve_slot: optional callable `(slot_text: str) -> str` that returns
      a Python expression for an LLM-resolved `{{...}}` slot. When None,
      SlotExpr renders as a placeholder string literal `"<unresolved
      slot: TEXT>"` so the snippet still parses + transpiles cleanly
      (the placeholder is the cohort-visible "still needs LLM" marker).
      When provided, SlotExpr renders to whatever the callable returns
      — typically a Python literal (`60`, `"red"`, `[1, 2, 3]`).
    collect_slots: optional list. When provided, every SlotExpr encountered
      during transpile appends `(slot_text, rendered_python_expr)` to this
      list — lets callers inventory what slots a recipe needs without
      having to walk the AST themselves.
  """
  global _active_resolve_slot, _active_slot_collector
  _active_resolve_slot = resolve_slot
  _active_slot_collector = collect_slots
  try:
    return _transpile_inner(module, inputs)
  finally:
    _active_resolve_slot = None
    _active_slot_collector = None


def _transpile_inner(module: Module, inputs) -> str:
  # Drain 2026-08-10-2000 — dedicated `Input` keyword. Retires the
  # drain-1610 positional-typed-Let-as-parameter inference AS THE
  # PRIMARY MECHANISM: when the Recipe has ANY `Input` statement
  # (anywhere — position is no longer load-bearing, unlike the old
  # leading-run rule), Input decls are the ONLY signature source and
  # EVERY typed Let (anywhere) renders as an annotated local instead
  # of being silently promoted or having its annotation dropped.
  #
  # Backward compat: a Recipe with ZERO Input statements falls back
  # to the drain-1610 leading-typed-Let promotion UNCHANGED (old
  # notes keep working with no edits), emitting a DeprecationWarning
  # when that fallback actually fires.
  from .parser import collect_typed_input_lets, _literal_value_of

  input_stmts = [s for s in module.statements if isinstance(s, InputStmt)]

  if input_stmts:
    required_parts = [
      f"{s.name}: {_render_type_hint(s.type_hint)}"
      for s in input_stmts if s.is_required
    ]
    defaulted_parts = [
      f"{s.name}: {_render_type_hint(s.type_hint)} = {_render_default(s.default)}"
      for s in input_stmts if not s.is_required
    ]
    input_names = {s.name for s in input_stmts}
    legacy = [d for d in (inputs or []) if d.name not in input_names]
    legacy_parts = [
      f"{d.name}={_render_default(d.default)}" if d.has_default else d.name
      for d in legacy
    ]
    legacy_required = [p for p, d in zip(legacy_parts, legacy) if not d.has_default]
    legacy_defaulted = [p for p, d in zip(legacy_parts, legacy) if d.has_default]
    all_parts = required_parts + legacy_required + defaulted_parts + legacy_defaulted
    # Input statements are pure signature declarations — omitted from
    # the body regardless of where they appeared in the source.
    body_stmts = [s for s in module.statements if not isinstance(s, InputStmt)]
  else:
    # Legacy fallback — drain 1610's exact behavior, unchanged.
    typed_lets = collect_typed_input_lets(module)
    if typed_lets:
      warnings.warn(
        "typed Let as a parameter declaration is deprecated; use the "
        "Input keyword instead (Input name: Type = default.)",
        DeprecationWarning,
        stacklevel=2,
      )
    typed_names = {let.name for let in typed_lets}
    legacy = [d for d in (inputs or []) if d.name not in typed_names]

    required_parts = [
      f"{let.name}: {_render_type_hint(let.type_hint)}"
      for let in typed_lets if let.is_required_input
    ]
    defaulted_parts = [
      f"{let.name}: {_render_type_hint(let.type_hint)} = {_render_default(_literal_value_of(let.value)[1])}"
      for let in typed_lets if not let.is_required_input
    ]
    legacy_parts = [
      f"{d.name}={_render_default(d.default)}" if d.has_default else d.name
      for d in legacy
    ]
    legacy_required = [p for p, d in zip(legacy_parts, legacy) if not d.has_default]
    legacy_defaulted = [p for p, d in zip(legacy_parts, legacy) if d.has_default]
    all_parts = required_parts + legacy_required + defaulted_parts + legacy_defaulted
    body_stmts = module.statements[len(typed_lets):]

  if all_parts:
    sig = f"def compute(context, {', '.join(all_parts)}):"
  else:
    sig = "def compute(context):"

  body_module = Module(statements=body_stmts)
  body_lines = _render_block(body_module.statements, depth=1)
  if not body_lines:
    body_lines = [INDENT + "pass"]
  out = sig + "\n" + "\n".join(body_lines) + "\n"
  # Drain 2000 Part 3 — inject the typing import iff an enum-literal
  # type hint anywhere (signature or a body-local annotation) actually
  # rendered to a Literal[...] expression. Checking the FINAL text is
  # simpler and equally correct vs. threading a flag through every
  # render call site.
  if "Literal[" in out:
    out = "from typing import Literal\n\n" + out
  return out


def _render_default(v):
  """repr() works for ints, floats, strings, bools, None, lists of literals."""
  return repr(v)


def _render_type_hint(type_hint: str) -> str:
  """Drain 2026-08-10-2000 Part 3 — render an E-- type-hint string as
  Python. Detects the enum-literal pattern (two or more `|`-separated
  quoted-string tokens, e.g. `'major' | 'minor'`) and renders it as
  `Literal["major", "minor"]`; every other type hint passes through
  verbatim (drain 1610's opaque passthrough, unchanged). The caller
  is responsible for injecting `from typing import Literal` when the
  rendered output actually contains a `Literal[` (checked post-hoc on
  the full transpiled text, not threaded through here)."""
  parts = [p.strip() for p in type_hint.split('|')]
  is_enum_literal = len(parts) >= 2 and all(
    len(p) >= 2 and p[0] == p[-1] and p[0] in ("'", '"')
    for p in parts
  )
  if not is_enum_literal:
    return type_hint
  values = [p[1:-1] for p in parts]
  return "Literal[" + ", ".join(repr(v) for v in values) + "]"


def _render_block(stmts, depth):
  out = []
  for s in stmts:
    out.extend(_render_stmt(s, depth))
  return out


def _render_stmt(stmt, depth):
  pad = INDENT * depth
  if isinstance(stmt, LetStmt):
    # Drain 2026-08-10-2000 Part 4 — a typed Let that reaches body
    # emission (i.e. wasn't promoted to a signature parameter, in
    # EITHER mode) keeps its annotation. Drain 1610 silently dropped
    # it here; that WAT is fixed unconditionally since a non-promoted
    # typed Let can only ever arrive at this line with a real value
    # (the only value-less LetStmt shape, `is_required_input`, is
    # only ever produced for LEADING Lets, which legacy-mode's
    # promotion always slices out of the body — see _transpile_inner).
    if stmt.type_hint is not None:
      return [f"{pad}{stmt.name}: {_render_type_hint(stmt.type_hint)} = {_render_expr(stmt.value)}"]
    return [f"{pad}{stmt.name} = {_render_expr(stmt.value)}"]
  if isinstance(stmt, ReturnStmt):
    if stmt.value is None:
      return [f"{pad}return None"]
    return [f"{pad}return {_render_expr(stmt.value)}"]
  if isinstance(stmt, CallStmt):
    arg_expr = "" if stmt.arg is None else _render_expr(stmt.arg)
    return [f"{pad}{_render_chip_invocation(stmt.name, arg_expr)}"]
  if isinstance(stmt, ExprStmt):
    # Top-level `Call [[name]] with k=v.` — render as the expression
    # on its own line, no assignment. Return value is discarded.
    return [f"{pad}{_render_expr(stmt.expr)}"]
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


def _render_chip_invocation(name: str, kwargs_pyexpr: str) -> str:
  """Render the Python form of a V2 chip invocation.

  Two shapes:

  - **Bare name** (`solitary`, `kick`): emit `name(kwargs)` — a direct
    call with NO runtime fallback. Whoever builds the execution scope
    must therefore have already put a `name` in it, or this dies at
    runtime with `NameError`.

    Two different components do that, and they are NOT the same code:
    `forge.core.executor`'s `_build_snippet_shims` registers shims keyed
    by basename with caller-aware sibling-subdir probing, while the
    forge-transpile sandbox emits module-scope defs only for notes the
    forge-mcp closure walker packaged. This docstring previously
    described only the former and implied it covered both, which sent
    drain 2026-08-12-2130's investigation down the wrong path: the real
    bug was that the closure walker's bare-name lookup checked the vault
    ROOT only, so `[[solitary]]` at `percussion_lab/solitary.md` was
    never packaged and no def was emitted. Fixed in forge-mcp's
    `vault_note_closure._find_note_id`; the asymmetry between the two
    scope-builders remains, so do not assume a bare name that resolves
    under one will resolve under the other.
  - **Path-shaped** (`forge-music/percussion_lab/solitary`): emit
    `context.compute("forge-music/percussion_lab/solitary", kwargs)`.
    The resolver handles the qualified path directly without needing
    the caller's directory for disambiguation. This is the V2 /generate
    LLM's natural output when it wants to call into another vault.

  Why distinguish: post-v0.2.185 the LLM produced
  `[[forge-music/percussion_lab/solitary]]` from a note in the bluh
  vault. v0.2.186's first attempt naively stripped to basename
  (`solitary`) — but bluh's resolver has no forge-music subdir context,
  so the shim's `context.compute("solitary")` failed with
  SnippetResolutionError. Routing path-shaped wikilinks straight
  through context.compute() preserves the LLM's qualification.
  """
  if "/" in name:
    if kwargs_pyexpr:
      return f"context.compute({name!r}, {kwargs_pyexpr})"
    return f"context.compute({name!r})"
  # Bare name → through the shim.
  if kwargs_pyexpr:
    return f"{name}({kwargs_pyexpr})"
  return f"{name}()"


def _render_expr(expr) -> str:
  if isinstance(expr, ChipCall):
    if expr.kwargs:
      kw = ", ".join(
        f"{k.name}={_render_expr(k.value)}" for k in expr.kwargs
      )
    else:
      kw = ""
    return _render_chip_invocation(expr.name, kw)
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
  if isinstance(expr, SlotExpr):
    if _active_resolve_slot is not None:
      rendered = _active_resolve_slot(expr.text)
    else:
      # Placeholder shape: a string literal that surfaces clearly in
      # output if execution proceeds with an unresolved slot. Mirrors
      # V1 vendored E--'s "resolve at emit time or fail loudly" stance.
      rendered = repr(f"<unresolved slot: {expr.text}>")
    if _active_slot_collector is not None:
      _active_slot_collector.append((expr.text, rendered))
    return rendered
  if isinstance(expr, BinaryOp):
    return f"({_render_expr(expr.left)} {expr.op} {_render_expr(expr.right)})"
  raise TypeError(f"unknown expression type: {type(expr).__name__}")
