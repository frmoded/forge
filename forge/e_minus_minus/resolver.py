"""Transpile-time `{{ }}` value-slot resolver (spec §4.4.1–§4.4.2).

`make_anthropic_resolver(...)` returns a `resolve(text) -> str` callable that:

- returns a cached Python-expression string on a cache hit (no model call);
- on a cache miss, asks an Anthropic model (Haiku by default) for a single
  Python expression, validates it parses with ``ast.parse(mode="eval")``
  (but NEVER executes it), writes it to a committed JSON cache, and returns it.

The resolver makes a model call only on a cache miss, and constructs the
Anthropic client lazily — so cache-only and mock paths need neither the
`anthropic` package nor an API key.
"""

from __future__ import annotations

import ast
import json
import os

from .errors import EmmResolveError

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = (
    "Translate the English description into a single Python expression that "
    "evaluates to that value. Output ONLY the Python expression on one line "
    "— no prose, no markdown, no code fences."
)


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


def make_anthropic_resolver(cache_path: str = ".emm_cache.json",
                            model: str = _DEFAULT_MODEL,
                            client=None):
    """Build a `resolve(text) -> str` slot resolver.

    `client` may be injected (e.g. a fake in tests, or a preconstructed
    Anthropic client); if None, a real client is constructed lazily on the
    first cache miss, requiring ``ANTHROPIC_API_KEY``.
    """
    state = {"client": client}

    def resolve(text: str) -> str:
        cache = _load_cache(cache_path)
        if text in cache:
            return cache[text]  # cache hit — no model call

        c = state["client"]
        if c is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise EmmResolveError(
                    "set ANTHROPIC_API_KEY to resolve {{ }} slots "
                    f"(no cached value for: {text!r})")
            try:
                import anthropic  # lazy: only needed on a live cache miss
            except ImportError as exc:
                raise EmmResolveError(
                    "the 'anthropic' package is required to resolve {{ }} "
                    "slots but is not installed. Run: "
                    "pip install -r requirements.txt") from exc
            c = anthropic.Anthropic(api_key=api_key)
            state["client"] = c

        try:
            response = c.messages.create(
                model=model,
                max_tokens=256,
                temperature=0,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
        except Exception as exc:  # SDK / transport / auth errors
            name = type(exc).__name__
            if "Authentication" in name or "invalid x-api-key" in str(exc):
                raise EmmResolveError(
                    f"Anthropic rejected the API key (authentication error) "
                    f"while resolving slot {text!r}. Check that "
                    f"ANTHROPIC_API_KEY is a valid, current key with no extra "
                    f"quotes or whitespace. Original error: {exc}") from exc
            raise EmmResolveError(
                f"LLM call failed while resolving slot {text!r}: "
                f"{name}: {exc}") from exc
        raw = response.content[0].text
        expr = _strip_fences(raw)

        try:
            ast.parse(expr, mode="eval")  # validate only — never execute
        except SyntaxError as exc:
            raise EmmResolveError(
                f"model did not return a valid Python expression for slot "
                f"{text!r}; got: {raw!r}") from exc

        cache[text] = expr
        _write_cache(cache_path, cache)
        return expr

    return resolve
