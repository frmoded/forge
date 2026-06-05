"""Phase 1 normalizer: free-English E-- -> canonical E-- (spec §1.3).

`make_normalizer(...)` returns a `normalize(source) -> str` callable that turns
a free-English (or mixed) E-- source into canonical E-- at **per-region**
granularity (the §1.3 target): canonical lines pass through byte-for-byte and
only English runs hit the LLM.

1. **Fast path (no LLM).** If ``parse(tokenize(source))`` succeeds, the whole
   source is already canonical — return it unchanged, no model call, no key.
2. **Classify + group.** Split into physical lines; classify each non-blank line
   as ``canonical`` or ``english`` with the single-line detector
   (``is_canonical_statement_line``); blank lines are neutral and attach to the
   current region. Group maximal consecutive runs of the same class into regions.
3. **Resolve each region.** ``canonical`` regions emit verbatim. ``english``
   regions are normalized via the LLM, **cached per region** (key = the region's
   exact text). The model is asked for canonical at indentation level 0, then the
   output is re-indented to the region's base indent so placement is
   deterministic.
4. **Stitch + validate.** Concatenate regions in order and ``parse(tokenize(...))``
   the whole result; un-parseable output raises ``EmmNormalizeError`` (never
   silently accepted).

Like the resolver, model calls happen only on a cache miss and the Anthropic
client is constructed lazily — so a fully-canonical file, a mixed file whose
English regions are all cached, and the mock path need neither the ``anthropic``
package nor an API key. The public ``make_normalizer``/``normalize`` contract is
unchanged from the whole-file version; only granularity, cost, and stability
improve.
"""

from __future__ import annotations

import json
import os

from .lexer import tokenize
from .parser import parse, is_canonical_statement_line
from .errors import EmmNormalizeError, EmmSyntaxError

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# A tight-but-complete canonical-E-- reference, drawn from spec §3, §4.3, §5,
# so the model emits valid canonical that the deterministic parser accepts.
_SYSTEM_PROMPT = """\
You translate free-form English into CANONICAL E-- ("English--"), a controlled \
English language that compiles deterministically to Python. Output ONLY the \
canonical E-- program — no prose, no explanation, no markdown code fences.

Canonical E-- is English with the ambiguity removed: a closed grammar, fixed \
verbs, and explicit markers. Significant indentation (Python-style) drives block \
structure; indent nested blocks by 4 spaces. End simple statements with a period.

STATEMENT VERBS (one canonical phrasing each):
- Set <var> to <expr>.                      assignment
- Do <expr>.                                evaluate for effect (e.g. a call)
- Give back <expr>.                         return
- If <cond>:                                if-block (body indented below)
- Otherwise if <cond>:                      elif-block
- Otherwise:                                else-block
- While <cond>:                             while-loop
- For each <var> in <expr>:                 for-loop
- Define [[name]] taking <params>:          function definition (params comma-separated bare words; "taking nothing" or "taking:" for none)

MARKERS:
- [[name]] is a function CALL: [[print]](x), [[describe]](n). A bare word is a VARIABLE.
- Literals: "text" is a string, 3 / 3.5 are numbers, True / False are booleans, Nothing is None.
- <a, b, c> is a LIST. {"k": v} is a DICT. <> is the empty list.
- {{ english phrase }} is an LLM value slot — keep such phrases verbatim inside {{ }} (do not resolve them).

OPERATORS (infix English; NO PRECEDENCE):
  a plus b | a minus b | a times b | a divided by b
  a is greater than b | a is less than b | a does not equal b
  a and b | a or b | not a (prefix)
  a is in b | a is not in b
Grouping rule: a flat chain of ONE repeated operator needs no parentheses \
(a plus b plus c). MIXING two different operators REQUIRES explicit grouping \
with ( ): write (2 plus 3) times 4, never 2 plus 3 times 4. `not` may not sit on \
either side of an infix operator without grouping: (not a) equals b, or \
not (a equals b).

Emit canonical at indentation level 0: the outermost statement(s) you produce \
must start flush-left (no leading spaces), with nested blocks indented 4 spaces \
relative to their header. The caller re-indents your output to its final \
position, so always start at the left margin.

Produce the most direct canonical translation of the user's program. Preserve \
identifiers and string contents. Emit nothing but the canonical program.
"""


def _load_cache(cache_path: str) -> dict:
    if not os.path.exists(cache_path):
        return {}
    with open(cache_path, "r", encoding="utf-8") as fh:
        data = fh.read().strip()
    if not data:
        return {}
    return json.loads(data)


def _write_cache(cache_path: str, cache: dict) -> None:
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, sort_keys=True, indent=2)
        fh.write("\n")


def _strip_fences(text: str) -> str:
    """Defensively remove markdown code fences and surrounding whitespace."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _parses_as_canonical(source: str) -> bool:
    """The parser is the canonical-detector: does this source parse cleanly?"""
    try:
        parse(tokenize(source))
        return True
    except EmmSyntaxError:
        return False


def _leading_ws(line: str) -> str:
    """The leading-whitespace prefix of ``line`` (spaces/tabs)."""
    return line[:len(line) - len(line.lstrip(" \t"))]


def _classify_regions(source: str):
    """Split ``source`` into ordered (cls, [lines]) regions.

    ``cls`` is ``"canonical"`` or ``"english"``. Non-blank lines are classified
    with the single-line detector; blank lines are neutral and attach to the
    current region (or, before any region, seed a leading canonical region that
    passes through verbatim). Maximal consecutive same-class runs are grouped.
    """
    regions = []  # list of [cls, [physical lines]]
    for line in source.splitlines():
        if line.strip() == "":
            cls = None  # blank: neutral
        elif is_canonical_statement_line(line):
            cls = "canonical"
        else:
            cls = "english"

        if cls is None:
            if regions:
                regions[-1][1].append(line)
            else:
                # Leading blank(s): pass through as canonical (verbatim).
                regions.append(["canonical", [line]])
        elif regions and regions[-1][0] == cls:
            regions[-1][1].append(line)
        else:
            regions.append([cls, [line]])
    return regions


def make_normalizer(cache_path: str = ".emm_norm_cache.json",
                    model: str = _DEFAULT_MODEL,
                    client=None):
    """Build a per-region `normalize(source) -> str` normalizer.

    `client` may be injected (e.g. a fake in tests, or a preconstructed
    Anthropic client); if None, a real client is constructed lazily on the
    first English-region cache miss, requiring ``ANTHROPIC_API_KEY``.
    """
    state = {"client": client}

    def _client():
        """Lazily obtain the Anthropic client (key check + import here)."""
        c = state["client"]
        if c is not None:
            return c
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EmmNormalizeError(
                "set ANTHROPIC_API_KEY to normalize free-English E-- to "
                "canonical (no cached canonical form for this region)")
        try:
            import anthropic  # lazy: only needed on a live cache miss
        except ImportError as exc:
            raise EmmNormalizeError(
                "the 'anthropic' package is required to normalize "
                "free-English E-- but is not installed. Run: "
                "pip install -r requirements.txt") from exc
        c = anthropic.Anthropic(api_key=api_key)
        state["client"] = c
        return c

    def _call_model(region_text: str) -> str:
        try:
            response = _client().messages.create(
                model=model,
                max_tokens=2048,
                temperature=0,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": region_text}],
            )
        except EmmNormalizeError:
            raise  # key/import errors from _client() pass through unchanged
        except Exception as exc:  # SDK / transport / auth errors
            name = type(exc).__name__
            if "Authentication" in name or "invalid x-api-key" in str(exc):
                raise EmmNormalizeError(
                    "Anthropic rejected the API key (authentication error) "
                    "while normalizing free-English E--. Check that "
                    "ANTHROPIC_API_KEY is a valid, current key with no extra "
                    f"quotes or whitespace. Original error: {exc}") from exc
            raise EmmNormalizeError(
                f"LLM call failed while normalizing source: "
                f"{name}: {exc}") from exc
        return _strip_fences(response.content[0].text)

    def normalize(source: str) -> str:
        # Step 0 — fast path: a fully-canonical file passes straight through.
        if _parses_as_canonical(source):
            return source

        # Steps 1-2 — classify lines and group into regions.
        regions = _classify_regions(source)
        cache = _load_cache(cache_path)
        cache_dirty = False

        # Step 3 — resolve each region.
        out_lines = []
        for cls, lines in regions:
            if cls == "canonical":
                out_lines.extend(lines)  # verbatim, byte-for-byte
                continue
            # English region: normalize via the LLM, cached by exact region text.
            region_text = "\n".join(lines)
            if region_text in cache:
                canonical_region = cache[region_text]
            else:
                base_indent = _leading_ws(lines[0])
                level0 = _call_model(region_text)
                canonical_region = "\n".join(
                    (base_indent + ln) if ln.strip() else ""
                    for ln in level0.split("\n"))
                cache[region_text] = canonical_region
                cache_dirty = True
            out_lines.extend(canonical_region.split("\n"))

        result = "\n".join(out_lines)

        # Step 4 — validate the stitched whole; never accept un-parseable output.
        try:
            parse(tokenize(result))
        except EmmSyntaxError as exc:
            raise EmmNormalizeError(
                "the stitched normalization did not parse as canonical E--. "
                f"Parse error: {exc}\n--- stitched output ---\n{result}"
            ) from exc

        if cache_dirty:
            _write_cache(cache_path, cache)
        return result

    return normalize
