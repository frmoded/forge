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
class RepeatStmt:
  count: "Expr"
  body: List["Stmt"]


@dataclass
class ForEachStmt:
  var: str
  iterable: "Expr"
  body: List["Stmt"]


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


Stmt = Union[LetStmt, ReturnStmt, CallStmt, RepeatStmt, ForEachStmt]
Expr = Union[ChipCall, ListLit, NumberLit, StringLit, IdentRef]


# --- Tokenizer ---------------------------------------------------------

# Token kinds: KEYWORD, IDENT, NUMBER, STRING, WIKILINK, OP, NEWLINE, INDENT, DEDENT, EOF.
# Keywords are lexed as IDENT then matched against this set:
_KEYWORDS = {"Let", "Return", "Call", "with", "Repeat", "times", "For", "each", "in"}


class ParseError(SyntaxError):
  """Raised on any E-- parse error. Includes line / col when available."""


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
    # Wikilink
    if src[i:i+2] == "[[":
      end = src.find("]]", i+2)
      if end == -1:
        raise ParseError(f"unclosed wikilink at line {line}, col {col}")
      name = src[i+2:end].strip()
      toks.append(Tok("WIKILINK", name, line, col))
      col += end + 2 - i; i = end + 2; continue
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
        raise ParseError(f"unterminated string at line {line}, col {col}")
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
    # Single-char ops: = , . [ ] :
    if ch in "=,.[]:":
      toks.append(Tok("OP", ch, line, col))
      i += 1; col += 1; continue
    raise ParseError(f"unexpected char {ch!r} at line {line}, col {col}")
  toks.append(Tok("EOF", "", line, col))
  return toks


# --- Line splitter -----------------------------------------------------

def _split_lines(src: str) -> List[tuple]:
  """Split E-- source into (indent_level, line_text) tuples. Strips
  blank lines and trailing whitespace. Indent measured in spaces (tabs
  expanded to 2 spaces, conventional for our snippets)."""
  out = []
  for raw in src.splitlines():
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
    out.append((indent, raw.strip()))
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
      indent, _ = self.lines[self.pos]
      if indent < base_indent:
        break
      stmt = self._parse_stmt()
      out.append(stmt)
    return out

  def _parse_stmt(self) -> Stmt:
    indent, text = self.lines[self.pos]
    # Block-header statements are detected on their first keyword.
    # Strip trailing EOF so downstream "look at toks[-1]" sees the real
    # last token of the line.
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
    if head.kind == "WIKILINK":
      self.pos += 1
      return self._parse_shorthand_call_body(toks)
    raise ParseError(f"unexpected start of statement: {head.value!r} on line {head.line}")

  # --- Statement bodies (toks is the tokenized form of a single line) ---

  def _parse_let_body(self, toks: List[Tok]) -> LetStmt:
    # Let IDENT = expr .
    if toks[1].kind != "IDENT":
      raise ParseError(f"expected identifier after Let, got {toks[1].value!r}")
    name = toks[1].value
    if not (toks[2].kind == "OP" and toks[2].value == "="):
      raise ParseError(f"expected = after Let {name}")
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
      raise ParseError("expected ':' at end of Repeat header")
    # toks[0] is "Repeat", last is ":", "times" is somewhere between.
    times_idx = _find_keyword(toks, "times")
    if times_idx is None:
      raise ParseError("Repeat header missing 'times' keyword")
    count_toks = toks[1:times_idx]
    count = _parse_expr(count_toks)
    body = self._parse_block(base_indent=header_indent + 1)
    return RepeatStmt(count=count, body=body)

  def _parse_foreach_body(self, toks: List[Tok], header_indent: int) -> ForEachStmt:
    # For each IDENT in expr :
    if not (toks[-1].kind == "OP" and toks[-1].value == ":"):
      raise ParseError("expected ':' at end of For-each header")
    if not (toks[1].kind == "KEYWORD" and toks[1].value == "each"):
      raise ParseError("expected 'each' after 'For'")
    if toks[2].kind != "IDENT":
      raise ParseError(f"expected variable identifier, got {toks[2].value!r}")
    var = toks[2].value
    if not (toks[3].kind == "KEYWORD" and toks[3].value == "in"):
      raise ParseError("expected 'in' after For-each variable")
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

def _parse_expr(toks: List[Tok]) -> Expr:
  """Parse a single expression from a flat token list. The token list must
  cover EXACTLY the expression (no trailing terminator).

  Supported forms (greedy, leftmost-first):
    - Call WIKILINK with kwargs   (chip call)
    - WIKILINK                    (bare = chip call with no args)
    - [ ... ]                     (list literal)
    - NUMBER                      (number literal)
    - STRING                      (string literal)
    - IDENT                       (variable reference)
  """
  if not toks:
    raise ParseError("empty expression")
  head = toks[0]
  # Chip call: Call [[name]] with k=v, ...
  if head.kind == "KEYWORD" and head.value == "Call":
    if not (len(toks) >= 2 and toks[1].kind == "WIKILINK"):
      raise ParseError("expected wikilink after Call")
    name = toks[1].value
    if len(toks) == 2:
      return ChipCall(name=name, kwargs=[])
    if not (toks[2].kind == "KEYWORD" and toks[2].value == "with"):
      raise ParseError("expected 'with' after Call <wikilink>")
    return ChipCall(name=name, kwargs=_parse_kwargs(toks[3:]))
  # Bare wikilink → call with no args
  if head.kind == "WIKILINK":
    if len(toks) > 1:
      raise ParseError(
        f"trailing tokens after bare wikilink: {toks[1].value!r} "
        "(use `Call [[name]] with ...` for parameterized calls)"
      )
    return ChipCall(name=head.value, kwargs=[])
  # List literal
  if head.kind == "OP" and head.value == "[":
    if not (toks[-1].kind == "OP" and toks[-1].value == "]"):
      raise ParseError("unclosed list literal")
    inner = toks[1:-1]
    if not inner:
      return ListLit(items=[])
    items = []
    for chunk in _split_top_level(inner, ","):
      items.append(_parse_expr(chunk))
    return ListLit(items=items)
  # Number
  if head.kind == "NUMBER" and len(toks) == 1:
    return NumberLit(value=_coerce_number(head.value))
  # String
  if head.kind == "STRING" and len(toks) == 1:
    return StringLit(value=head.value)
  # Identifier (variable ref)
  if head.kind == "IDENT" and len(toks) == 1:
    return IdentRef(name=head.value)
  raise ParseError(f"unrecognized expression starting with {head.value!r}")


def _parse_kwargs(toks: List[Tok]) -> List[Kwarg]:
  """Parse: IDENT = expr , IDENT = expr , ... — return list of Kwarg."""
  out: List[Kwarg] = []
  for chunk in _split_top_level(toks, ","):
    if len(chunk) < 3 or chunk[0].kind != "IDENT":
      raise ParseError(f"malformed kwarg starting at {chunk[0].value!r}")
    if not (chunk[1].kind == "OP" and chunk[1].value == "="):
      raise ParseError(f"expected = after kwarg name {chunk[0].value!r}")
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
