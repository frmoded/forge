"""System-prompt assembly for /generate.

The core machinery (forge.core.llm) imports this module and asks for the
final assembled prompt. Domain-specific guidance (music, future arch / moda /
…) lives in per-domain modules that call register_fragment(...) at import
time.

For v1, every registered fragment is included unconditionally. Future scope-
aware filtering (e.g., only include music when a music vault is in scope) is
a non-breaking extension of build_system_prompt.

Future expansions:
  forge.arch.llm_prompt   # IFC / building output guidance, when that lands
  forge.moda.llm_prompt   # whatever modal-domain ends up meaning
"""

from typing import List, Optional

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

Output ONLY valid Python code. No markdown fences, no explanation, no comments."""


_fragments: List[str] = []


def register_fragment(fragment: str) -> None:
  """Register a domain-specific block to be appended to the system prompt.

  Idempotent: a fragment registered twice is included once. Domain modules
  call this at import time.
  """
  cleaned = fragment.strip()
  if cleaned and cleaned not in _fragments:
    _fragments.append(cleaned)


def build_system_prompt(active_domains: Optional[List[str]] = None) -> str:
  """Assemble the final system prompt as base + every registered fragment.

  `active_domains` is reserved for future scope-aware filtering and ignored
  for v1.
  """
  del active_domains  # not used yet
  parts = [BASE_SYSTEM_PROMPT.rstrip()]
  parts.extend(_fragments)
  return "\n\n".join(parts) + "\n"


def registered_fragments() -> List[str]:
  """Read-only view, useful for tests."""
  return list(_fragments)
