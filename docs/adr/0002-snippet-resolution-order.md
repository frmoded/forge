# ADR 0002: Snippet resolution order

## Status
Accepted — 2026-04-28

## Context
A running Forge instance has multiple sources of snippets active at
once: the user's authoring vault, library vaults installed from the
registry and declared in the authoring vault's manifest, and the
built-in vault shipped with the `forge` package (per ADR 0001).
Snippets can share bare names across these sources. The resolver must
behave deterministically so users (and the LLM-generated code that
references snippets) get predictable behavior.

## Decision
For bare snippet references — e.g., `[[install]]` or
`context.execute("install")` — Forge resolves in the following order
and returns the first match:

1. The authoring vault (the user's primary working vault).
2. Declared library vaults, in the order listed in the authoring
   vault's `forge.toml` `dependencies` array.
3. The built-in vault (`forge`).

For qualified references — e.g., `[[3js/sphere]]` or
`context.execute("forge/install")` — resolution skips the order entirely
and goes directly to the named vault. If the named vault is not loaded,
the resolver raises a structured error.

If a bare reference matches no source, the resolver raises:
"Snippet '<name>' not found. Searched: <authoring vault>, <library
vault names>, forge (built-in)."

If a snippet of the same name exists in multiple sources, only the
first match is returned. The shadowed snippets are still callable via
qualified references.

## Consequences
- Users can locally override library or built-in snippets simply by
  creating a snippet of the same name in their authoring vault.
- Resolution mirrors familiar conventions from programming languages
  (Python's `sys.path[0]` precedence, Rust's prelude, JavaScript's
  module resolution).
- Forge's resolver and Obsidian's wikilink resolver may behave
  differently when names are ambiguous: Obsidian flags ambiguity in
  its UI; Forge resolves silently using order. This is acceptable —
  users authoring across multiple vaults are encouraged to use
  qualified references for clarity.
- Manifest dependency order becomes meaningful, not just declarative.
  This must be documented for users who add multiple library vaults.