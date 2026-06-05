"""Python emitter for the E-- deterministic core.

Walks a ``Program`` AST and produces Python source text with 4-space
indentation. ``{{ }}`` slots are resolved via the injected ``resolve_slot``
callable, whose return value is spliced in as already-literal Python text
(spec §4.4).
"""

from __future__ import annotations

from .ast_nodes import (
    Assign, Do, Return, If, While, ForEach, Define, Program,
    Num, Str, Bool, NoneLit, Var, Call, ListLit, DictLit, LlmSlot, Group,
    BinOp, UnaryOp,
)

INDENT_UNIT = "    "  # 4 spaces

# Canonical operator phrase -> Python operator (spec §4.3).
_OP_MAP = {
    "plus": "+",
    "minus": "-",
    "times": "*",
    "divided by": "/",
    "modulo": "%",
    "to the power of": "**",
    "is greater than": ">",
    "is less than": "<",
    "is at least": ">=",
    "is at most": "<=",
    "equals": "==",
    "does not equal": "!=",
    "and": "and",
    "or": "or",
    "is in": "in",
    "is not in": "not in",
}


def emit(program: Program, resolve_slot) -> str:
    lines = []
    for stmt in program.statements:
        lines.extend(_emit_stmt(stmt, 0, resolve_slot))
    return "\n".join(lines)


def _emit_stmt(stmt, level, resolve_slot):
    pad = INDENT_UNIT * level
    if isinstance(stmt, Assign):
        return [f"{pad}{stmt.target} = {_emit_expr(stmt.value, resolve_slot)}"]
    if isinstance(stmt, Do):
        return [f"{pad}{_emit_expr(stmt.call, resolve_slot)}"]
    if isinstance(stmt, Return):
        return [f"{pad}return {_emit_expr(stmt.value, resolve_slot)}"]
    if isinstance(stmt, If):
        lines = [f"{pad}if {_emit_expr(stmt.cond, resolve_slot)}:"]
        lines += _emit_body(stmt.body, level + 1, resolve_slot)
        for elif_cond, elif_body in stmt.elifs:
            lines.append(f"{pad}elif {_emit_expr(elif_cond, resolve_slot)}:")
            lines += _emit_body(elif_body, level + 1, resolve_slot)
        if stmt.else_body is not None:
            lines.append(f"{pad}else:")
            lines += _emit_body(stmt.else_body, level + 1, resolve_slot)
        return lines
    if isinstance(stmt, While):
        head = f"{pad}while {_emit_expr(stmt.cond, resolve_slot)}:"
        return [head] + _emit_body(stmt.body, level + 1, resolve_slot)
    if isinstance(stmt, ForEach):
        head = (f"{pad}for {stmt.var} in "
                f"{_emit_expr(stmt.iterable, resolve_slot)}:")
        return [head] + _emit_body(stmt.body, level + 1, resolve_slot)
    if isinstance(stmt, Define):
        params = _emit_params(stmt.params, resolve_slot)
        head = f"{pad}def {stmt.name}({params}):"
        return [head] + _emit_body(stmt.body, level + 1, resolve_slot)
    raise TypeError(f"unknown statement node: {type(stmt).__name__}")


def _emit_body(stmts, level, resolve_slot):
    lines = []
    for stmt in stmts:
        lines.extend(_emit_stmt(stmt, level, resolve_slot))
    return lines


def _emit_params(params, resolve_slot):
    parts = []
    for name, default in params:
        if default is None:
            parts.append(name)
        else:
            parts.append(f"{name}={_emit_expr(default, resolve_slot)}")
    return ", ".join(parts)


def _emit_expr(node, resolve_slot):
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Str):
        return f'"{node.value}"'
    if isinstance(node, Bool):
        return "True" if node.value else "False"
    if isinstance(node, NoneLit):
        return "None"
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Call):
        parts = [_emit_expr(a, resolve_slot) for a in node.args]
        parts += [f"{k}={_emit_expr(v, resolve_slot)}" for k, v in node.kwargs]
        return f"{node.name}({', '.join(parts)})"
    if isinstance(node, ListLit):
        items = ", ".join(_emit_expr(i, resolve_slot) for i in node.items)
        return f"[{items}]"
    if isinstance(node, DictLit):
        entries = ", ".join(
            f"{_emit_expr(k, resolve_slot)}: {_emit_expr(v, resolve_slot)}"
            for k, v in node.entries)
        return f"{{{entries}}}"
    if isinstance(node, LlmSlot):
        resolved = resolve_slot(node.text)
        return str(resolved)
    if isinstance(node, Group):
        return f"({_emit_expr(node.expr, resolve_slot)})"
    if isinstance(node, BinOp):
        pyop = _OP_MAP[node.op]
        left = _emit_expr(node.left, resolve_slot)
        right = _emit_expr(node.right, resolve_slot)
        return f"{left} {pyop} {right}"
    if isinstance(node, UnaryOp):
        return f"not {_emit_expr(node.operand, resolve_slot)}"
    raise TypeError(f"unknown expression node: {type(node).__name__}")
