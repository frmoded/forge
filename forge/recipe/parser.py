"""V2 E-- parser — hand-written recursive-descent per v2-spike §3.2 Pick A.

Grammar (subset for the v2-spike — full V2 grammar can extend later):

  module      := stmt*
  stmt        := let | return | shorthand_call | repeat | foreach
  let         := "Let" IDENT "=" expr "."
  return      := "Return" expr? "."
  shorthand_call := WIKILINK expr? "."        ; positional shorthand (0 or 1 arg)
  repeat      := "Repeat" expr "times" ":" block
  foreach     := "For" "each" IDENT "in" expr ":" block
  block       := indented stmt+

  expr        := chip_call | wikilink_expr | list_lit | number | string | ident
  chip_call   := "Call" WIKILINK ("with" kwargs)?
  kwargs      := kwarg ("," kwarg)*
  kwarg       := IDENT "=" expr
  wikilink_expr := WIKILINK                   ; bare wikilink = call with no args
  list_lit    := "[" (expr ("," expr)*)? "]"

The grammar is line-aware (Let / Return / shorthand_call end with `.`;
Repeat / For begin a `:`-terminated header and an indented block).
Indentation is significant for blocks but tokens within a line are
whitespace-insensitive otherwise.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union


# --- AST ---------------------------------------------------------------

@dataclass
class Module:
  statements: List["Stmt"] = field(default_factory=list)


@dataclass
class LetStmt:
  name: str
  value: "Expr"


@dataclass
class ReturnStmt:
  value: Optional["Expr"]


@dataclass
class CallStmt:
  """Bare shorthand call as a statement (e.g. `[[show_score]] part.`)."""
  name: str
  arg: Optional["Expr"]   # the single positional arg, or None for bare


@dataclass
class ExprStmt:
  """A top-level expression evaluated for its side effect (typically a
  `Call [[name]] with ...` whose return value is discarded). v0.2.185 —
  added because the V2 /generate LLM produced
      Call [[print]] with text="hi".
      Call [[print]] with text="bye".
      Return.
  and the parser previously rejected `Call` at statement position,
  forcing every side-effect call to be wrapped in `Let _ = ...`.
  Transpiler renders ExprStmt as the expression on its own line, no
  assignment."""
  expr: "Expr"


@dataclass
class RepeatStmt:
  count: "Expr"
  body: List["Stmt"]


@dataclass
class ForEachStmt:
  var: str
  iterable: "Expr"
  body: List["Stmt"]


@dataclass
class IfStmt:
  condition: "Expr"
  then_body: List["Stmt"]
  else_body: List["Stmt"]   # empty if no Otherwise


@dataclass
class BinaryOp:
  op: str   # one of '+', '-', '*', '/', '<=', '<', '>=', '>', '==', '!='
  left: "Expr"
  right: "Expr"


@dataclass
class ChipCall:
  """Inline call expression: Call [[name]] with k=v, ... — or a bare
  wikilink (when used in expression position) which is `Call [[name]]`
  with no args."""
  name: str
  kwargs: List["Kwarg"] = field(default_factory=list)


@dataclass
class Kwarg:
  name: str
  value: "Expr"


@dataclass
class NumberLit:
  value: float   # int values stay int via _coerce_number


@dataclass
class StringLit:
  value: str


@dataclass
class ListLit:
  items: List["Expr"]


@dataclass
class IdentRef:
  name: str


@dataclass
class BoolLit:
  value: bool


@dataclass
class NoneLit:
  pass


@dataclass
class SlotExpr:
  """`{{free english here}}` — an LLM-resolved single expression slot
  (v2-spec §5.2). Parser produces SlotExpr; transpiler renders it by
  calling an injected `resolve_slot(text)` callable. The resolver
  returns a Python expression string that gets substituted at
  transpile time. Mirrors V1 vendored E--'s `LlmSlot` shape so V2 can
  reuse the same caching machinery (`forge.core.slot_cache` +
  `forge-transpile /resolve-slot`)."""
  text: str   # the free text between {{ and }}, stripped


Stmt = Union[LetStmt, ReturnStmt, CallStmt, ExprStmt, RepeatStmt, ForEachStmt, IfStmt]
Expr = Union[ChipCall, ListLit, NumberLit, StringLit, IdentRef, BoolLit, NoneLit, BinaryOp, SlotExpr]


# --- Tokenizer ---------------------------------------------------------

# Token kinds: KEYWORD, IDENT, NUMBER, STRING, WIKILINK, OP, NEWLINE, INDENT, DEDENT, EOF.
# Keywords are lexed as IDENT then matched against this set:
_KEYWORDS = {"Let", "Return", "Call", "with", "Repeat", "times", "For", "each", "in",
             "If", "Otherwise"}


class ParseError(SyntaxError):
  """Raised on any E-- parse error.

  Extends `SyntaxError` (its own `.lineno` / `.offset` / `.msg`) so callers
  can `except SyntaxError` interchangeably. Location fields are set
  structurally via the `lineno` + `col_offset` kwargs at every raise site
  where the parser knows the token's position; message text no longer
  duplicates "at line X, col Y" (drain 2026-07-14-1235 — downstream
  consumers like `/compile` and the plugin error UI can now read structured
  `.lineno` / `.col_offset` directly instead of regex-parsing the message).

  `col_offset` mirrors `SyntaxError.offset` — set both so the SyntaxError
  surface reports the location too (traceback / `ast` compat).

  `lineno=None` (default) means the raise site legitimately doesn't have
  a token position in hand — the caller should treat missing position as
  "unknown", not "line 0" (avoids the pre-drain-1235 confusion where
  `line: 0` in downstream JSON could mean either "line 0 of source" or
  "no location info").
  """

  def __init__(
    self,
    msg: str,
    *,
    lineno: Optional[int] = None,
    col_offset: Optional[int] = None,
  ) -> None:
    super().__init__(msg)
    self.msg = msg
    self.lineno = lineno
    # SyntaxError.offset is 1-indexed by Python convention; the parser's
    # token `col` is 1-indexed too, so pass through as-is.
    self.offset = col_offset
    # Alias for consumers that prefer the `ast`-style name.
    self.col_offset = col_offset


@dataclass
class Tok:
  kind: str
  value: str
  line: int
  col: int


def _tokenize(src: str) -> List[Tok]:
  """Lex a single LOGICAL LINE into tokens. Block structure (indent /
  dedent) is handled by the parser, not the lexer. This keeps the lexer
  pure-string and order-independent."""
  toks: List[Tok] = []
  i = 0
  line = 1
  col = 1
  while i < len(src):
    ch = src[i]
    if ch in " \t":
      i += 1; col += 1; continue
    if ch == "\n":
      i += 1; line += 1; col = 1; continue
    # Slot — `{{ free english here }}`. Greedy-match content between the
    # opening `{{` and the next `}}`. Empty slot (`{{}}`) is a parse
    # error (no expression to resolve). Single-line only; newlines
    # inside a slot raise. Mirrors V1 vendored E--'s LlmSlot lex shape.
    if src[i:i+2] == "{{":
      j = i + 2
      while j < len(src) - 1:
        if src[j:j+2] == "}}":
          break
        if src[j] == "\n":
          raise ParseError(
            "unterminated slot (no closing '}}' on line)",
            lineno=line, col_offset=col,
          )
        j += 1
      else:
        # Reached end without finding `}}`.
        raise ParseError(
          "unterminated slot (no closing '}}')",
          lineno=line, col_offset=col,
        )
      text = src[i+2:j].strip()
      if not text:
        raise ParseError(
          "empty slot '{{}}'",
          lineno=line, col_offset=col,
        )
      if "{{" in text:
        raise ParseError(
          "nested slot '{{...{{...}}...}}'",
          lineno=line, col_offset=col,
        )
      toks.append(Tok("SLOT", text, line, col))
      col += j + 2 - i; i = j + 2; continue
    # Wikilink — accepts a hierarchical snippet path like
    # `[[forge-music/percussion_lab/solitary]]`. First char must be a
    # letter or `_` so `[[0,2,3], [0]]` (nested list literal as a
    # kwarg value) doesn't greedy-match the leading `0` as the first
    # wikilink char. Subsequent chars accept the broader Forge bare-id
    # character set: alphanumeric + `_` + `/` (path separator) + `-`
    # (hyphen, used in vault names like `forge-music`).
    #
    # v0.2.186 — pre-fix only accepted `[a-zA-Z0-9_]`, which made the
    # V2 /generate LLM's natural `[[forge-music/percussion_lab/solitary]]`
    # output unlexable (smoke 2 ParseError "expected wikilink after
    # Call"). The widened character set matches the existing snippet
    # bare-id format that `_build_snippet_shims` keys on; the
    # transpiler's `_render_chip_name` strips the path prefix to the
    # leaf basename for the actual Python call (matches shim convention).
    if src[i:i+2] == "[[":
      probe = i + 2
      # First content char must be alpha or `_` (rules out numeric
      # list literals that happen to look bracket-shaped).
      if probe < len(src) and (src[probe].isalpha() or src[probe] == "_"):
        probe += 1
        while probe < len(src) and (
          src[probe].isalnum()
          or src[probe] in ("_", "/", "-")
        ):
          probe += 1
        if src[probe:probe+2] == "]]":
          name = src[i+2:probe]
          toks.append(Tok("WIKILINK", name, line, col))
          col += probe + 2 - i; i = probe + 2; continue
      # Not a valid wikilink — fall through and emit a single `[` OP.
      toks.append(Tok("OP", "[", line, col))
      i += 1; col += 1; continue
    # Number — consume `.` only if followed by a digit, so `1.` is
    # NumberLit(1) + OP('.') terminator rather than the malformed "1." token.
    if ch.isdigit() or (ch == "-" and i+1 < len(src) and src[i+1].isdigit()):
      j = i + 1
      while j < len(src):
        if src[j].isdigit():
          j += 1
        elif src[j] == "." and j+1 < len(src) and src[j+1].isdigit():
          j += 1
        else:
          break
      toks.append(Tok("NUMBER", src[i:j], line, col))
      col += j - i; i = j; continue
    # String (single or double quoted, no escaping for spike)
    if ch in ("'", '"'):
      quote = ch
      j = i + 1
      while j < len(src) and src[j] != quote:
        j += 1
      if j >= len(src):
        raise ParseError("unterminated string", lineno=line, col_offset=col)
      toks.append(Tok("STRING", src[i+1:j], line, col))
      col += j - i + 1; i = j + 1; continue
    # Identifier / keyword
    if ch.isalpha() or ch == "_":
      j = i + 1
      while j < len(src) and (src[j].isalnum() or src[j] == "_"):
        j += 1
      word = src[i:j]
      kind = "KEYWORD" if word in _KEYWORDS else "IDENT"
      toks.append(Tok(kind, word, line, col))
      col += j - i; i = j; continue
    # Multi-char comparison ops: <=, >=, ==, !=
    if src[i:i+2] in ("<=", ">=", "==", "!="):
      toks.append(Tok("OP", src[i:i+2], line, col))
      i += 2; col += 2; continue
    # Single-char ops: = , . [ ] : + - * / < >
    if ch in "=,.[]:+-*/<>":
      toks.append(Tok("OP", ch, line, col))
      i += 1; col += 1; continue
    raise ParseError(f"unexpected char {ch!r}", lineno=line, col_offset=col)
  toks.append(Tok("EOF", "", line, col))
  return toks


# --- Line splitter -----------------------------------------------------

def _split_lines(src: str) -> List[tuple]:
  """Split E-- source into (indent_level, line_text, source_lineno)
  tuples. `source_lineno` is 1-indexed and refers to the ORIGINAL source
  (skipped blank lines still consume line numbers, so a parse error on
  the third non-blank line reports the right lineno even if the second
  original line was blank). Strips blank lines and trailing whitespace.
  Indent measured in spaces (tabs expanded to 2 spaces, conventional for
  our snippets).

  Drain 2026-07-14-1235 added `source_lineno` so `_parse_stmt` can
  translate the tokenizer's per-line-relative `line=1` back to the
  original source line when a ParseError bubbles up."""
  out = []
  for i, raw in enumerate(src.splitlines(), start=1):
    text = raw.rstrip()
    if not text.strip():
      continue
    indent = 0
    for ch in raw:
      if ch == " ":
        indent += 1
      elif ch == "\t":
        indent += 2
      else:
        break
    out.append((indent, raw.strip(), i))
  return out


# --- Parser ------------------------------------------------------------

class _Parser:
  def __init__(self, lines: List[tuple]):
    self.lines = lines
    self.pos = 0

  def _peek_indent(self) -> Optional[int]:
    if self.pos >= len(self.lines):
      return None
    return self.lines[self.pos][0]

  def parse_module(self) -> Module:
    stmts = self._parse_block(base_indent=0)
    return Module(statements=stmts)

  def _parse_block(self, base_indent: int) -> List[Stmt]:
    """Parse statements at indent >= base_indent, stopping at end or
    when indent drops below base_indent."""
    out: List[Stmt] = []
    while self.pos < len(self.lines):
      indent = self.lines[self.pos][0]
      if indent < base_indent:
        break
      stmt = self._parse_stmt()
      out.append(stmt)
    return out

  def _parse_stmt(self) -> Stmt:
    indent, text, source_lineno = self.lines[self.pos]
    # Block-header statements are detected on their first keyword.
    # Strip trailing EOF so downstream "look at toks[-1]" sees the real
    # last token of the line.
    # Drain 2026-07-14-1235: `_tokenize` is called per-line and always
    # emits tokens with `line=1`. Wrap the body in try/except so any
    # ParseError raised with a per-line-relative `lineno` gets shifted
    # to the ORIGINAL source line before propagating.
    #
    # Guarded by a `_source_line_shifted` sentinel so nested `_parse_stmt`
    # calls (e.g. Repeat / For-each / If bodies each open their own
    # `_parse_block` which recursively calls `_parse_stmt`) don't double-
    # shift a lineno that was already translated by a deeper recursion.
    # Leaves lineno=None untouched (raise sites like "empty expression"
    # that have no location).
    try:
      return self._parse_stmt_body(indent, text)
    except ParseError as exc:
      if exc.lineno is not None and not getattr(exc, "_source_line_shifted", False):
        exc.lineno = source_lineno + (exc.lineno - 1)
        exc._source_line_shifted = True
      raise

  def _parse_stmt_body(self, indent: int, text: str) -> Stmt:
    toks = _tokenize(text)
    if toks and toks[-1].kind == "EOF":
      toks = toks[:-1]
    head = toks[0]
    if head.kind == "KEYWORD" and head.value == "Let":
      self.pos += 1
      return self._parse_let_body(toks)
    if head.kind == "KEYWORD" and head.value == "Return":
      self.pos += 1
      return self._parse_return_body(toks)
    if head.kind == "KEYWORD" and head.value == "Repeat":
      self.pos += 1
      header_indent = indent
      return self._parse_repeat_body(toks, header_indent)
    if head.kind == "KEYWORD" and head.value == "For":
      self.pos += 1
      header_indent = indent
      return self._parse_foreach_body(toks, header_indent)
    if head.kind == "KEYWORD" and head.value == "If":
      self.pos += 1
      header_indent = indent
      return self._parse_if_body(toks, header_indent)
    if head.kind == "WIKILINK":
      self.pos += 1
      return self._parse_shorthand_call_body(toks)
    if head.kind == "KEYWORD" and head.value == "Call":
      # v0.2.185 — `Call [[name]] with k=v, k=v.` at top-level is a
      # side-effect statement. Parse the whole line (minus trailing
      # `.`) as a single expression and wrap as ExprStmt. The expr
      # parser already handles `Call`-prefix chip calls correctly.
      self.pos += 1
      expr_toks, _tail = _split_at_terminator(toks, ".")
      if not expr_toks:
        raise ParseError(
          "empty Call statement",
          lineno=head.line, col_offset=head.col,
        )
      expr = _parse_expr(expr_toks)
      return ExprStmt(expr=expr)
    raise ParseError(
      f"unexpected start of statement: {head.value!r}",
      lineno=head.line, col_offset=head.col,
    )

  # --- Statement bodies (toks is the tokenized form of a single line) ---

  def _parse_let_body(self, toks: List[Tok]) -> LetStmt:
    # Let IDENT = expr .
    if toks[1].kind != "IDENT":
      raise ParseError(
        f"expected identifier after Let, got {toks[1].value!r}",
        lineno=toks[1].line, col_offset=toks[1].col,
      )
    name = toks[1].value
    if not (toks[2].kind == "OP" and toks[2].value == "="):
      raise ParseError(
        f"expected = after Let {name}",
        lineno=toks[2].line, col_offset=toks[2].col,
      )
    expr_toks, _tail = _split_at_terminator(toks[3:], ".")
    expr = _parse_expr(expr_toks)
    return LetStmt(name=name, value=expr)

  def _parse_return_body(self, toks: List[Tok]) -> ReturnStmt:
    # Return expr? .
    body = toks[1:]
    expr_toks, _tail = _split_at_terminator(body, ".")
    if not expr_toks:
      return ReturnStmt(value=None)
    expr = _parse_expr(expr_toks)
    return ReturnStmt(value=expr)

  def _parse_shorthand_call_body(self, toks: List[Tok]) -> CallStmt:
    # WIKILINK expr? .
    name = toks[0].value
    body = toks[1:]
    expr_toks, _tail = _split_at_terminator(body, ".")
    if not expr_toks:
      return CallStmt(name=name, arg=None)
    arg = _parse_expr(expr_toks)
    return CallStmt(name=name, arg=arg)

  def _parse_repeat_body(self, toks: List[Tok], header_indent: int) -> RepeatStmt:
    # Repeat expr times :
    # Body: stmts at indent > header_indent
    if not (toks[-1].kind == "OP" and toks[-1].value == ":"):
      raise ParseError(
        "expected ':' at end of Repeat header",
        lineno=toks[0].line, col_offset=toks[0].col,
      )
    # toks[0] is "Repeat", last is ":", "times" is somewhere between.
    times_idx = _find_keyword(toks, "times")
    if times_idx is None:
      raise ParseError(
        "Repeat header missing 'times' keyword",
        lineno=toks[0].line, col_offset=toks[0].col,
      )
    count_toks = toks[1:times_idx]
    count = _parse_expr(count_toks)
    body = self._parse_block(base_indent=header_indent + 1)
    return RepeatStmt(count=count, body=body)

  def _parse_if_body(self, toks: List[Tok], header_indent: int) -> IfStmt:
    # If <expr> :
    # <indented then-block>
    # [Otherwise:
    #   <indented else-block>]
    if not (toks[-1].kind == "OP" and toks[-1].value == ":"):
      raise ParseError(
        "expected ':' at end of If header",
        lineno=toks[0].line, col_offset=toks[0].col,
      )
    condition = _parse_expr(toks[1:-1])
    then_body = self._parse_block(base_indent=header_indent + 1)
    else_body: List[Stmt] = []
    # Look-ahead: does the next line at header_indent start with `Otherwise:`?
    if self.pos < len(self.lines):
      next_indent, next_text, _next_lineno = self.lines[self.pos]
      if next_indent == header_indent:
        next_toks = _tokenize(next_text)
        # strip EOF
        if next_toks and next_toks[-1].kind == "EOF":
          next_toks = next_toks[:-1]
        if (next_toks and next_toks[0].kind == "KEYWORD"
            and next_toks[0].value == "Otherwise"
            and len(next_toks) >= 2
            and next_toks[1].kind == "OP" and next_toks[1].value == ":"):
          self.pos += 1
          else_body = self._parse_block(base_indent=header_indent + 1)
    return IfStmt(condition=condition, then_body=then_body, else_body=else_body)


  def _parse_foreach_body(self, toks: List[Tok], header_indent: int) -> ForEachStmt:
    # For each IDENT in expr :
    if not (toks[-1].kind == "OP" and toks[-1].value == ":"):
      raise ParseError(
        "expected ':' at end of For-each header",
        lineno=toks[0].line, col_offset=toks[0].col,
      )
    if not (toks[1].kind == "KEYWORD" and toks[1].value == "each"):
      raise ParseError(
        "expected 'each' after 'For'",
        lineno=toks[1].line, col_offset=toks[1].col,
      )
    if toks[2].kind != "IDENT":
      raise ParseError(
        f"expected variable identifier, got {toks[2].value!r}",
        lineno=toks[2].line, col_offset=toks[2].col,
      )
    var = toks[2].value
    if not (toks[3].kind == "KEYWORD" and toks[3].value == "in"):
      raise ParseError(
        "expected 'in' after For-each variable",
        lineno=toks[3].line, col_offset=toks[3].col,
      )
    iterable_toks = toks[4:-1]
    iterable = _parse_expr(iterable_toks)
    body = self._parse_block(base_indent=header_indent + 1)
    return ForEachStmt(var=var, iterable=iterable, body=body)


def _split_at_terminator(toks: List[Tok], terminator: str) -> tuple:
  """Return (toks_before, toks_after) split at the LAST terminator OP. If
  no terminator found, the entire list is `before` and `after` is []."""
  for i in range(len(toks) - 1, -1, -1):
    if toks[i].kind == "OP" and toks[i].value == terminator:
      return toks[:i], toks[i+1:]
  return toks, []


def _find_keyword(toks: List[Tok], kw: str) -> Optional[int]:
  for i, t in enumerate(toks):
    if t.kind == "KEYWORD" and t.value == kw:
      return i
  return None


# --- Expression parser -------------------------------------------------

_BINOP_PRECEDENCE = {
  "==": 1, "!=": 1, "<": 1, "<=": 1, ">": 1, ">=": 1,
  "+": 2, "-": 2,
  "*": 3, "/": 3,
}


def _parse_expr(toks: List[Tok]) -> Expr:
  """Parse a single expression from a flat token list. Handles binary
  operators (arithmetic + comparisons) via precedence climbing — primary
  expressions (chip calls, literals, identifiers, lists) parse via
  `_parse_primary` and are then composed with `+`, `-`, `*`, `/`, `==`,
  `<=`, etc.

  Special case: `Call [[name]] with k=v, k=v` consumes ALL remaining
  tokens — no top-level binop split. Internal kwarg values can have
  their own binops; `_parse_kwargs` handles those per-kwarg via
  `_parse_expr` recursively.
  """
  if not toks:
    # No tokens → no location. Callers of _parse_expr on empty slices
    # (e.g., missing kwarg values) will re-raise with their own context;
    # leaving lineno=None here per drain 2026-07-14-1235 §Don'ts (avoid
    # a "location unknown" sentinel; use None).
    raise ParseError("empty expression")
  if toks[0].kind == "KEYWORD" and toks[0].value == "Call":
    return _parse_primary(toks)
  # When a chip call appears later in the expression (e.g.
  # `n * Call [[f]] with x=1`), the `Call` consumes ALL tokens after it
  # — internal binops in kwarg values are handled by _parse_kwargs
  # recursing back into _parse_expr. So when scanning for top-level
  # binops, we stop at the first `Call` keyword.
  call_pos = None
  for i, t in enumerate(toks):
    if t.kind == "KEYWORD" and t.value == "Call":
      call_pos = i
      break
  binop_scan_end = call_pos if call_pos is not None else len(toks)
  # Split at the LOWEST-precedence top-level binary operator (right-to-left
  # so leftmost-grouping wins on equal precedence). Stops at `[` / `]`
  # nesting depth tracking so list literals' internal commas + comparisons
  # don't get split.
  best_idx = -1
  best_prec = 999
  depth = 0
  for i in range(binop_scan_end):
    t = toks[i]
    if t.kind == "OP" and t.value == "[":
      depth += 1; continue
    if t.kind == "OP" and t.value == "]":
      depth -= 1; continue
    if depth > 0:
      continue
    if t.kind == "OP" and t.value in _BINOP_PRECEDENCE:
      # Skip leading `-` (unary negation handled by lexer/primary path).
      if i == 0 and t.value == "-":
        continue
      prec = _BINOP_PRECEDENCE[t.value]
      if prec <= best_prec:
        best_idx = i
        best_prec = prec
  if best_idx > 0:
    left = _parse_expr(toks[:best_idx])
    right = _parse_expr(toks[best_idx+1:])
    return BinaryOp(op=toks[best_idx].value, left=left, right=right)
  return _parse_primary(toks)


def _parse_primary(toks: List[Tok]) -> Expr:
  """Parse a primary (non-binary-op) expression. Covers:
    - Call WIKILINK with kwargs
    - WIKILINK (bare = parameterless call)
    - [ ... ] (list literal)
    - NUMBER / STRING / IDENT / True / False / None
  """
  if not toks:
    # See _parse_expr comment above — no location for the empty case.
    raise ParseError("empty expression")
  head = toks[0]
  # Chip call: Call [[name]] with k=v, ...
  if head.kind == "KEYWORD" and head.value == "Call":
    if not (len(toks) >= 2 and toks[1].kind == "WIKILINK"):
      raise ParseError(
        "expected wikilink after Call",
        lineno=head.line, col_offset=head.col,
      )
    name = toks[1].value
    if len(toks) == 2:
      return ChipCall(name=name, kwargs=[])
    if not (toks[2].kind == "KEYWORD" and toks[2].value == "with"):
      raise ParseError(
        "expected 'with' after Call <wikilink>",
        lineno=toks[2].line, col_offset=toks[2].col,
      )
    return ChipCall(name=name, kwargs=_parse_kwargs(toks[3:]))
  # Bare wikilink → call with no args
  if head.kind == "WIKILINK":
    if len(toks) > 1:
      raise ParseError(
        f"trailing tokens after bare wikilink: {toks[1].value!r} "
        "(use `Call [[name]] with ...` for parameterized calls)",
        lineno=toks[1].line, col_offset=toks[1].col,
      )
    return ChipCall(name=head.value, kwargs=[])
  # List literal
  if head.kind == "OP" and head.value == "[":
    if not (toks[-1].kind == "OP" and toks[-1].value == "]"):
      raise ParseError(
        "unclosed list literal",
        lineno=head.line, col_offset=head.col,
      )
    inner = toks[1:-1]
    if not inner:
      return ListLit(items=[])
    items = []
    for chunk in _split_top_level(inner, ","):
      items.append(_parse_expr(chunk))
    return ListLit(items=items)
  # LLM slot — `{{free english}}` resolves to a Python expression at
  # transpile time via the executor's injected resolve_slot callable.
  if head.kind == "SLOT" and len(toks) == 1:
    return SlotExpr(text=head.value)
  # Number
  if head.kind == "NUMBER" and len(toks) == 1:
    return NumberLit(value=_coerce_number(head.value))
  # String
  if head.kind == "STRING" and len(toks) == 1:
    return StringLit(value=head.value)
  # Identifier (variable ref) — also handles bool / None literals which
  # share the IDENT lexing pathway. Python-style casing only (True / False
  # / None) so the transpile output drops in cleanly as Python.
  if head.kind == "IDENT" and len(toks) == 1:
    if head.value == "True":
      return BoolLit(value=True)
    if head.value == "False":
      return BoolLit(value=False)
    if head.value == "None":
      return NoneLit()
    return IdentRef(name=head.value)
  raise ParseError(
    f"unrecognized expression starting with {head.value!r}",
    lineno=head.line, col_offset=head.col,
  )


def _parse_kwargs(toks: List[Tok]) -> List[Kwarg]:
  """Parse: IDENT = expr , IDENT = expr , ... — return list of Kwarg."""
  out: List[Kwarg] = []
  for chunk in _split_top_level(toks, ","):
    if len(chunk) < 3 or chunk[0].kind != "IDENT":
      raise ParseError(
        f"malformed kwarg starting at {chunk[0].value!r}",
        lineno=chunk[0].line, col_offset=chunk[0].col,
      )
    if not (chunk[1].kind == "OP" and chunk[1].value == "="):
      raise ParseError(
        f"expected = after kwarg name {chunk[0].value!r}",
        lineno=chunk[1].line, col_offset=chunk[1].col,
      )
    out.append(Kwarg(name=chunk[0].value, value=_parse_expr(chunk[2:])))
  return out


def _split_top_level(toks: List[Tok], sep: str) -> List[List[Tok]]:
  """Split a flat token list at OP `sep`, respecting bracket / paren
  nesting (treats `[` / `]` as one level of nesting)."""
  out: List[List[Tok]] = []
  cur: List[Tok] = []
  depth = 0
  for t in toks:
    if t.kind == "OP" and t.value == "[":
      depth += 1; cur.append(t)
    elif t.kind == "OP" and t.value == "]":
      depth -= 1; cur.append(t)
    elif t.kind == "OP" and t.value == sep and depth == 0:
      if cur:
        out.append(cur)
        cur = []
    else:
      cur.append(t)
  if cur:
    out.append(cur)
  return out


def _coerce_number(s: str):
  if "." in s:
    return float(s)
  return int(s)


# --- Public entry point ------------------------------------------------

def parse(src: str) -> Module:
  """Parse E-- source into a Module AST."""
  lines = _split_lines(src)
  return _Parser(lines).parse_module()
