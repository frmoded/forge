"""System-prompt assembly for /generate.

The core machinery (forge.core.llm) imports this module and asks for the
final assembled prompt. Domain-specific guidance (music, future arch / moda /
…) lives in per-domain modules that call register_fragment(...) at import
time.

Fragments are keyed by domain name. build_system_prompt(active_domains)
filters which domains' fragments are included (constitution B9 /
domain-scoping): None = all (back-compat for vaults that don't declare
`domains` in forge.toml), [] = none (core-only), [...] = exactly those.

Future expansions:
  forge.arch.llm_prompt   # IFC / building output guidance, when that lands
"""

from typing import Dict, List, Optional

BASE_SYSTEM_PROMPT = """You are a code generator for the Forge snippet system.

Forge snippets are Python functions. Follow these conventions exactly:
- Every snippet's entrypoint must be named `compute`.
- Snippets with no inputs:      def compute(context): ...
- Snippets with named inputs:   def compute(context, param1, param2): ...
- Place ALL executable logic inside `compute`. Do not write top-level
  code that builds module state. Forge calls `compute(context)` — nothing
  else. Module-level statements other than imports and the `compute`
  definition are dead code.
- Call another snippet:         context.compute("snippet_id", param=value)
- Read an input parameter:      context.get("key", default)
- Side-effect output:           print(...)
- Return the result value at the end of the function.

General modules in scope (do NOT import them): random, math, numpy.

NEVER write any `import` or `from ... import ...` statements. The modules
listed throughout this prompt are already bound as global names in the
snippet's namespace — just use them directly. The runtime sandbox blocks
imports, so any import line will crash the snippet at execution time.

Data snippet return contract:
- TEXT data snippets (json, yaml, text, markdown, svg, musicxml) return the
  native python value. context.compute("config_json") -> dict;
  context.compute("notes_md") -> str.
- BINARY data snippets (image/jpeg, image/png, audio/mpeg, audio/wav,
  video/mp4) return a (bytes, content_type) tuple. ALWAYS unpack at the
  call site so it's clear you're handling raw bytes plus a MIME tag:
      data, ct = context.compute("cat_reference")
  Treating the return as a single value will produce a tuple in places
  that expect bytes — write the unpacking line.

`generation_notes` frontmatter field:
- Snippets may carry a `generation_notes` field in their frontmatter — a
  free-text block holding machine-targeted guidance (data shapes,
  idiomatic patterns, edge cases, carve-outs) that would clutter the
  English facet. When generating Python for a snippet whose frontmatter
  has this field, treat it as authoritative authoring context alongside
  the English facet. The English facet stays human-readable; the notes
  are how the author talks specifically to you.
- `generation_notes` from OTHER snippets is NOT visible in your
  authoring inventory — it's implementation-side, not part of the
  callable interface. Treat peer snippets as black boxes characterized
  by their name, signature, and English facet only.

Output ONLY valid Python code. No markdown fences, no explanation, no comments."""


# domain name -> fragment text. Insertion order preserved (py3.7+ dict)
# so the assembled prompt is stable across runs.
_fragments: Dict[str, str] = {}


def register_fragment(domain: str, fragment: str) -> None:
  """Register a domain-specific prompt block under `domain`.

  Domain modules call this at import time, e.g.
  register_fragment("moda", MODA_PROMPT_FRAGMENT). Idempotent per
  domain: re-registering the same domain replaces its text (a module
  re-import on uvicorn --reload is a no-op rather than a duplicate).
  """
  cleaned = (fragment or "").strip()
  if domain and cleaned:
    _fragments[domain] = cleaned


def build_system_prompt(active_domains: Optional[List[str]] = None) -> str:
  """Assemble the system prompt: base + the active domains' fragments.

  active_domains:
    None  -> include ALL registered fragments (back-compat: vault did
             not declare `domains` in forge.toml).
    []    -> include NO domain fragments (core-only mode).
    [...] -> include only fragments whose domain is in the list, in
             registration order.
  """
  parts = [BASE_SYSTEM_PROMPT.rstrip()]
  if active_domains is None:
    parts.extend(_fragments.values())
  else:
    allow = set(active_domains)
    parts.extend(
      text for dom, text in _fragments.items() if dom in allow
    )
  return "\n\n".join(parts) + "\n"


def registered_fragments() -> List[str]:
  """Read-only list of fragment texts (registration order). For tests."""
  return list(_fragments.values())


def registered_domains() -> List[str]:
  """Read-only list of registered domain names. For tests / diagnostics."""
  return list(_fragments.keys())
