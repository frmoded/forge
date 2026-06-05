"""Lexer for canonical E-- source.

Produces a flat list of ``Token`` objects with Python-style INDENT / DEDENT /
NEWLINE tokens to drive block structure (spec §5.1). Multi-word keywords and
operator phrases are matched by longest-match against fixed tables (spec §4.3).
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import EmmSyntaxError


@dataclass
class Token:
    kind: str
    value: str
    line: int


# Keyword / verb / literal phrases (case-sensitive). Maps word-tuple -> kind.
# Value stored on the token is the joined phrase.
_KEYWORDS = {
    ("Set",): "SET",
    ("to",): "TO",
    ("Do",): "DO",
    ("Give", "back"): "GIVEBACK",
    ("If",): "IF",
    ("Otherwise", "if"): "OTHERWISE_IF",
    ("Otherwise",): "OTHERWISE",
    ("While",): "WHILE",
    ("For", "each"): "FOREACH",
    ("in",): "IN",
    ("Define",): "DEFINE",
    ("taking",): "TAKING",
    ("nothing",): "NOTHING_PARAMS",
    ("defaulting", "to"): "DEFAULTING_TO",
    ("True",): "TRUE",
    ("False",): "FALSE",
    ("Nothing",): "NONE",
}

# Operator phrases (spec §4.3). All emit kind "OP" with the canonical phrase
# as the token value.
_OPERATORS = {
    ("plus",),
    ("minus",),
    ("times",),
    ("divided", "by"),
    ("modulo",),
    ("to", "the", "power", "of"),
    ("is", "greater", "than"),
    ("is", "less", "than"),
    ("is", "at", "least"),
    ("is", "at", "most"),
    ("equals",),
    ("does", "not", "equal"),
    ("and",),
    ("or",),
    ("not",),
    ("is", "in"),
    ("is", "not", "in"),
}

# Unified match table: word-tuple -> (kind, value)
_MATCH = {}
for _words, _kind in _KEYWORDS.items():
    _MATCH[_words] = (_kind, " ".join(_words))
for _words in _OPERATORS:
    _MATCH[_words] = ("OP", " ".join(_words))

_MAX_PHRASE = max(len(w) for w in _MATCH)


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _scan_line(text: str, lineno: int) -> list:
    """Scan one physical line's content (no leading indent) into raw tokens.

    Word tokens are emitted as kind WORD; coalescing into keywords/operators
    happens in a later pass.
    """
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == " " or ch == "\t":
            i += 1
            continue
        # String literal
        if ch == '"':
            j = i + 1
            buf = []
            closed = False
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                if c == '"':
                    closed = True
                    break
                buf.append(c)
                j += 1
            if not closed:
                raise EmmSyntaxError(
                    f"line {lineno}: unterminated string literal")
            tokens.append(Token("STRING", "".join(buf), lineno))
            i = j + 1
            continue
        # Number literal: -?\d+(\.\d+)?  (scanned before '.' terminator)
        if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
            j = i + 1
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] == "." and j + 1 < n and text[j + 1].isdigit():
                j += 1
                while j < n and text[j].isdigit():
                    j += 1
            tokens.append(Token("NUMBER", text[i:j], lineno))
            i = j
            continue
        # Two-char structural tokens
        two = text[i:i + 2]
        if two == "[[":
            tokens.append(Token("LCALL", "[[", lineno)); i += 2; continue
        if two == "]]":
            tokens.append(Token("RCALL", "]]", lineno)); i += 2; continue
        if two == "{{":
            tokens.append(Token("LSLOT", "{{", lineno)); i += 2; continue
        if two == "}}":
            tokens.append(Token("RSLOT", "}}", lineno)); i += 2; continue
        # Single-char structural tokens
        single = {
            "(": "LPAREN", ")": "RPAREN",
            "<": "LANGLE", ">": "RANGLE",
            "{": "LBRACE", "}": "RBRACE",
            ",": "COMMA", ":": "COLON", ".": "DOT",
            "=": "EQ",
        }
        if ch in single:
            tokens.append(Token(single[ch], ch, lineno)); i += 1; continue
        # Word
        if _is_ident_start(ch):
            j = i + 1
            while j < n and _is_ident_char(text[j]):
                j += 1
            tokens.append(Token("WORD", text[i:j], lineno)); i = j; continue
        raise EmmSyntaxError(f"line {lineno}: unexpected character {ch!r}")
    return tokens


def _scan_slot(text: str, i: int, lineno: int):
    """Scan a {{ ... }} slot starting after the opening {{ at index i.

    Returns (slot_text, new_index_after_closing_}}).
    Slots are scanned raw so their free English is not lexed as E--.
    """
    n = len(text)
    buf = []
    while i < n:
        if text[i:i + 2] == "}}":
            return "".join(buf).strip(), i + 2
        buf.append(text[i])
        i += 1
    raise EmmSyntaxError(f"line {lineno}: unterminated {{{{ slot")


def _coalesce(raw: list) -> list:
    """Merge runs of WORD tokens into keywords / operators / identifiers."""
    out = []
    i = 0
    n = len(raw)
    while i < n:
        tok = raw[i]
        if tok.kind != "WORD":
            out.append(tok)
            i += 1
            continue
        # Gather the maximal run of WORD tokens.
        run = []
        while i < n and raw[i].kind == "WORD":
            run.append(raw[i])
            i += 1
        k = 0
        m = len(run)
        while k < m:
            matched = False
            for length in range(min(_MAX_PHRASE, m - k), 0, -1):
                key = tuple(t.value for t in run[k:k + length])
                if key in _MATCH:
                    kind, value = _MATCH[key]
                    out.append(Token(kind, value, run[k].line))
                    k += length
                    matched = True
                    break
            if not matched:
                out.append(Token("IDENT", run[k].value, run[k].line))
                k += 1
    return out


def tokenize(source: str) -> list:
    """Tokenize canonical E-- source into a flat token list.

    Emits NEWLINE at the end of each logical line and INDENT / DEDENT tokens
    to mark block nesting, then a final EOF.
    """
    raw = []
    indent_stack = [0]
    lines = source.splitlines()
    for idx, physical in enumerate(lines, start=1):
        # Determine indentation (leading spaces; tabs count as 1 each here).
        stripped = physical.lstrip(" \t")
        if stripped == "":
            continue  # blank line: no tokens, no indentation effect
        indent = len(physical) - len(stripped)

        # Pre-scan the line, extracting {{ }} slots raw before normal scanning.
        line_tokens = []
        pos = 0
        segment_start = 0
        text = physical
        n = len(text)
        # We need slot extraction interleaved with normal scanning, so scan
        # the line in pieces split on slots.
        pieces = []  # ("code", text) or ("slot", slot_text)
        scan_i = indent
        buf_start = scan_i
        in_string = False
        while scan_i < n:
            if not in_string and text[scan_i] == '"':
                in_string = True
                scan_i += 1
                continue
            if in_string:
                if text[scan_i] == "\\" and scan_i + 1 < n:
                    scan_i += 2
                    continue
                if text[scan_i] == '"':
                    in_string = False
                scan_i += 1
                continue
            if text[scan_i:scan_i + 2] == "{{":
                pieces.append(("code", text[buf_start:scan_i]))
                slot_text, after = _scan_slot(text, scan_i + 2, idx)
                pieces.append(("slot", slot_text))
                scan_i = after
                buf_start = scan_i
                continue
            scan_i += 1
        pieces.append(("code", text[buf_start:n]))

        for kind, payload in pieces:
            if kind == "code":
                line_tokens.extend(_scan_line(payload, idx))
            else:
                line_tokens.append(Token("SLOT", payload, idx))

        if not line_tokens:
            continue

        # Apply indentation tokens.
        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            raw.append(Token("INDENT", "", idx))
        else:
            while indent < indent_stack[-1]:
                indent_stack.pop()
                raw.append(Token("DEDENT", "", idx))
            if indent != indent_stack[-1]:
                raise EmmSyntaxError(
                    f"line {idx}: inconsistent indentation")

        raw.extend(line_tokens)
        raw.append(Token("NEWLINE", "", idx))

    while len(indent_stack) > 1:
        indent_stack.pop()
        raw.append(Token("DEDENT", "", len(lines)))
    raw.append(Token("EOF", "", len(lines)))

    return _coalesce(raw)
