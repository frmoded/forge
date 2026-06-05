"""AST node definitions for the E-- deterministic core.

Statements and expressions are plain dataclasses. The parser produces a
``Program`` of statements; the emitter walks them to produce Python source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --- Expressions ---------------------------------------------------------

@dataclass
class Num:
    value: str  # raw numeric text, e.g. "42" or "3.14" or "-1"


@dataclass
class Str:
    value: str  # the string contents WITHOUT surrounding quotes


@dataclass
class Bool:
    value: bool


@dataclass
class NoneLit:
    pass


@dataclass
class Var:
    name: str


@dataclass
class Call:
    name: str
    args: list  # positional expression nodes
    kwargs: list = field(default_factory=list)  # list of (name: str, expr) tuples


@dataclass
class ListLit:
    items: list  # list of expression nodes


@dataclass
class DictLit:
    entries: list  # list of (key_expr, value_expr) tuples


@dataclass
class LlmSlot:
    text: str  # the free text between {{ and }}, stripped


@dataclass
class Group:
    expr: object  # a single inner expression


@dataclass
class BinOp:
    op: str  # canonical operator phrase, e.g. "plus", "is greater than"
    left: object
    right: object


@dataclass
class UnaryOp:
    op: str  # currently only "not"
    operand: object


# --- Statements ----------------------------------------------------------

@dataclass
class Assign:
    target: str  # variable name
    value: object  # expression node


@dataclass
class Do:
    call: object  # a Call expression node


@dataclass
class Return:
    value: object  # expression node


@dataclass
class If:
    cond: object
    body: list  # list of statement nodes (the governing If branch)
    elifs: list = field(default_factory=list)  # list of (cond, body) tuples
    else_body: Optional[list] = None  # statement list, or None if no else


@dataclass
class While:
    cond: object
    body: list


@dataclass
class ForEach:
    var: str
    iterable: object
    body: list


@dataclass
class Define:
    name: str
    params: list  # list of (name, default_or_None) tuples
    body: list


@dataclass
class Program:
    statements: list = field(default_factory=list)
