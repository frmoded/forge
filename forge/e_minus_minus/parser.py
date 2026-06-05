"""Recursive-descent parser for canonical E-- (spec §4, §5).

Consumes the token list from ``lexer.tokenize`` and produces a ``Program``.
Enforces the no-precedence rule (spec §4.3): a chain must use one identical
operator, mixing requires explicit grouping, and ``not`` binds a single
operand and cannot combine with an infix operator unless grouped.
"""

from __future__ import annotations

from .errors import EmmSyntaxError
from .lexer import tokenize
from .ast_nodes import (
    Assign, Do, Return, If, While, ForEach, Define, Program,
    Num, Str, Bool, NoneLit, Var, Call, ListLit, DictLit, LlmSlot, Group,
    BinOp, UnaryOp,
)


class _Stream:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i]

    def next(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect(self, kind):
        tok = self.tokens[self.i]
        if tok.kind != kind:
            raise EmmSyntaxError(
                f"line {tok.line}: expected {kind}, got {tok.kind} "
                f"({tok.value!r})")
        self.i += 1
        return tok


def parse(tokens) -> Program:
    s = _Stream(tokens)
    statements = []
    while s.peek().kind != "EOF":
        statements.append(_statement(s))
    return Program(statements)


# --- Statements ----------------------------------------------------------

def _statement(s: _Stream):
    kind = s.peek().kind
    if kind == "SET":
        s.next()
        name = s.expect("IDENT").value
        s.expect("TO")
        value = _expression(s)
        s.expect("DOT")
        s.expect("NEWLINE")
        return Assign(name, value)
    if kind == "DO":
        s.next()
        call = _operand(s)
        if not isinstance(call, Call):
            raise EmmSyntaxError(
                f"line {s.peek().line}: 'Do' requires a call, got "
                f"{type(call).__name__}")
        s.expect("DOT")
        s.expect("NEWLINE")
        return Do(call)
    if kind == "GIVEBACK":
        s.next()
        value = _expression(s)
        s.expect("DOT")
        s.expect("NEWLINE")
        return Return(value)
    if kind == "IF":
        s.next()
        cond = _expression(s)
        s.expect("COLON")
        body = _block(s)
        elifs = []
        while s.peek().kind == "OTHERWISE_IF":
            s.next()
            elif_cond = _expression(s)
            s.expect("COLON")
            elif_body = _block(s)
            elifs.append((elif_cond, elif_body))
        else_body = None
        if s.peek().kind == "OTHERWISE":
            s.next()
            s.expect("COLON")
            else_body = _block(s)
            nxt = s.peek().kind
            if nxt == "OTHERWISE":
                raise EmmSyntaxError(
                    f"line {s.peek().line}: at most one 'Otherwise' per 'If' "
                    f"chain")
            if nxt == "OTHERWISE_IF":
                raise EmmSyntaxError(
                    f"line {s.peek().line}: 'Otherwise if' cannot follow "
                    f"'Otherwise' ('Otherwise' must be last)")
        return If(cond, body, elifs, else_body)
    if kind in ("OTHERWISE", "OTHERWISE_IF"):
        tok = s.peek()
        raise EmmSyntaxError(
            f"line {tok.line}: '{tok.value}' without a matching 'If'")
    if kind == "WHILE":
        s.next()
        cond = _expression(s)
        s.expect("COLON")
        body = _block(s)
        return While(cond, body)
    if kind == "FOREACH":
        s.next()
        var = s.expect("IDENT").value
        s.expect("IN")
        iterable = _expression(s)
        s.expect("COLON")
        body = _block(s)
        return ForEach(var, iterable, body)
    if kind == "DEFINE":
        s.next()
        s.expect("LCALL")
        name = s.expect("IDENT").value
        s.expect("RCALL")
        s.expect("TAKING")
        params = _params(s)
        s.expect("COLON")
        body = _block(s)
        return Define(name, params, body)
    tok = s.peek()
    raise EmmSyntaxError(
        f"line {tok.line}: expected a statement verb, got {tok.kind} "
        f"({tok.value!r})")


def _statement_head(s: _Stream):
    """Parse a single statement *or* block header, WITHOUT a following block.

    Simple statements (``Set``/``Do``/``Give back``) are parsed through their
    terminating ``.``; compound/continuation forms (``If``/``Otherwise if``/
    ``Otherwise``/``While``/``For each``/``Define``) are parsed through their
    ``:`` header only. Used by the single-line canonical detector — it never
    consumes a block, so a header with no body still validates.
    """
    kind = s.peek().kind
    if kind == "SET":
        s.next(); s.expect("IDENT"); s.expect("TO"); _expression(s)
        s.expect("DOT"); return
    if kind == "DO":
        s.next(); call = _operand(s)
        if not isinstance(call, Call):
            raise EmmSyntaxError("'Do' requires a call")
        s.expect("DOT"); return
    if kind == "GIVEBACK":
        s.next(); _expression(s); s.expect("DOT"); return
    if kind == "IF":
        s.next(); _expression(s); s.expect("COLON"); return
    if kind == "OTHERWISE_IF":
        s.next(); _expression(s); s.expect("COLON"); return
    if kind == "OTHERWISE":
        s.next(); s.expect("COLON"); return
    if kind == "WHILE":
        s.next(); _expression(s); s.expect("COLON"); return
    if kind == "FOREACH":
        s.next(); s.expect("IDENT"); s.expect("IN"); _expression(s)
        s.expect("COLON"); return
    if kind == "DEFINE":
        s.next(); s.expect("LCALL"); s.expect("IDENT"); s.expect("RCALL")
        s.expect("TAKING"); _params(s); s.expect("COLON"); return
    raise EmmSyntaxError(
        f"not a canonical statement head: {s.peek().kind}")


def is_canonical_statement_line(text: str) -> bool:
    """True iff ``text`` is one valid canonical statement or block header.

    Whitespace-insensitive (the line is stripped first), body-independent (a
    block header with no body still counts), and **never raises** — any lexer
    or parse error means "not canonical". Real English prose fails to match the
    rigid verbs/markers and so classifies as non-canonical.
    """
    stripped = text.strip()
    if not stripped:
        return False
    try:
        tokens = tokenize(stripped)
    except Exception:
        return False
    try:
        s = _Stream(tokens)
        _statement_head(s)
        # Exactly one statement/header per line: only a trailing NEWLINE + EOF
        # may remain.
        if s.peek().kind == "NEWLINE":
            s.next()
        return s.peek().kind == "EOF"
    except EmmSyntaxError:
        return False
    except Exception:
        return False


def _block(s: _Stream):
    s.expect("NEWLINE")
    s.expect("INDENT")
    stmts = []
    while s.peek().kind != "DEDENT":
        if s.peek().kind == "EOF":
            raise EmmSyntaxError("unexpected end of input inside block")
        stmts.append(_statement(s))
    s.expect("DEDENT")
    if not stmts:
        raise EmmSyntaxError("block must contain at least one statement")
    return stmts


def _params(s: _Stream):
    if s.peek().kind == "NOTHING_PARAMS":
        s.next()
        return []
    params = []
    name = s.expect("IDENT").value
    default = None
    if s.peek().kind == "DEFAULTING_TO":
        s.next()
        default = _expression(s)
    params.append((name, default))
    while s.peek().kind == "COMMA":
        s.next()
        name = s.expect("IDENT").value
        default = None
        if s.peek().kind == "DEFAULTING_TO":
            s.next()
            default = _expression(s)
        params.append((name, default))
    return params


# --- Expressions ---------------------------------------------------------

def _expression(s: _Stream):
    # Prefix `not`: binds a single operand; cannot combine with infix unless
    # grouped (spec §4.3).
    if s.peek().kind == "OP" and s.peek().value == "not":
        s.next()
        operand = _operand(s)
        node = UnaryOp("not", operand)
        if s.peek().kind == "OP":
            raise EmmSyntaxError(
                f"line {s.peek().line}: result of 'not' must be grouped to "
                f"combine with operator {s.peek().value!r}")
        return node

    left = _operand(s)
    if s.peek().kind != "OP":
        return left

    op = s.peek().value
    if op == "not":
        raise EmmSyntaxError(
            f"line {s.peek().line}: unexpected 'not' in infix position")
    node = left
    while s.peek().kind == "OP":
        cur = s.peek().value
        if cur == "not":
            raise EmmSyntaxError(
                f"line {s.peek().line}: unexpected 'not' in infix position")
        if cur != op:
            raise EmmSyntaxError(
                f"line {s.peek().line}: mixed operators {op!r} and {cur!r} "
                f"require explicit grouping")
        s.next()
        right = _operand(s)
        node = BinOp(op, node, right)  # left-associative
    return node


def _operand(s: _Stream):
    tok = s.peek()
    kind = tok.kind
    if kind == "NUMBER":
        s.next()
        return Num(tok.value)
    if kind == "STRING":
        s.next()
        return Str(tok.value)
    if kind == "TRUE":
        s.next()
        return Bool(True)
    if kind == "FALSE":
        s.next()
        return Bool(False)
    if kind == "NONE":
        s.next()
        return NoneLit()
    if kind == "SLOT":
        s.next()
        return LlmSlot(tok.value)
    if kind == "IDENT":
        s.next()
        return Var(tok.value)
    if kind == "LCALL":
        return _call(s)
    if kind == "LANGLE":
        return _list(s)
    if kind == "LBRACE":
        return _dict(s)
    if kind == "LPAREN":
        # Grouping: a '(' not immediately following ']]' opens a group.
        s.next()
        inner = _expression(s)
        s.expect("RPAREN")
        return Group(inner)
    if kind == "OP" and tok.value == "not":
        raise EmmSyntaxError(
            f"line {tok.line}: 'not' result must be grouped to be used here")
    raise EmmSyntaxError(
        f"line {tok.line}: expected an operand, got {kind} ({tok.value!r})")


def _call(s: _Stream):
    s.expect("LCALL")
    name = s.expect("IDENT").value
    s.expect("RCALL")
    s.expect("LPAREN")  # call args: '(' immediately follows ']]'
    args = []
    kwargs = []
    if s.peek().kind != "RPAREN":
        _arg(s, args, kwargs)
        while s.peek().kind == "COMMA":
            s.next()
            _arg(s, args, kwargs)
    s.expect("RPAREN")
    return Call(name, args, kwargs)


def _arg(s: _Stream, args, kwargs):
    """Parse one call argument into ``args`` (positional) or ``kwargs``.

    Keyword vs positional is decided by two-token lookahead: an argument is a
    keyword iff the current token is IDENT and the next is EQ. Ordering is
    enforced — a positional argument may not follow a keyword argument
    (spec §4.1).
    """
    tok = s.peek()
    nxt = s.tokens[s.i + 1] if s.i + 1 < len(s.tokens) else None
    is_keyword = (tok.kind == "IDENT" and nxt is not None and nxt.kind == "EQ")
    if is_keyword:
        kw_name = s.next().value   # IDENT
        s.next()                   # EQ
        kwargs.append((kw_name, _expression(s)))
        return
    if kwargs:
        raise EmmSyntaxError(
            f"line {tok.line}: positional argument after keyword argument")
    args.append(_expression(s))


def _list(s: _Stream):
    s.expect("LANGLE")
    items = []
    if s.peek().kind != "RANGLE":
        items.append(_expression(s))
        while s.peek().kind == "COMMA":
            s.next()
            items.append(_expression(s))
    s.expect("RANGLE")
    return ListLit(items)


def _dict(s: _Stream):
    s.expect("LBRACE")
    entries = []
    if s.peek().kind != "RBRACE":
        key = _expression(s)
        s.expect("COLON")
        val = _expression(s)
        entries.append((key, val))
        while s.peek().kind == "COMMA":
            s.next()
            key = _expression(s)
            s.expect("COLON")
            val = _expression(s)
            entries.append((key, val))
    s.expect("RBRACE")
    return DictLit(entries)
