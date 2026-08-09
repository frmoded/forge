# Forge structured error format (3-field shape)

**Introduced**: drain 2026-08-08-1300
(CW-plugin-plus-mcp-structured-error-format-parity).
**Implementations**: forge-client-obsidian `src/forge-error-core.ts`
(Forge Output panel) and forge-mcp `src/forge_mcp/error_response.py`
(tool responses). Both sides link here; this doc is the single source
of truth for the shape and its rendering conventions.

## The shape

```
cause          string   one sentence: what went wrong.
                        e.g. "Two notes share the basename 'X'."
suggested_fix  string   one sentence: the action the caller can take.
                        e.g. "Rename one to disambiguate."
details        string?  full traceback / debug data. Optional —
                        ABSENT beats empty (never emit an empty
                        string; omit the field).
```

Field names are identical on both surfaces (snake_case, including in
TypeScript) — parity is the point.

## Writing quality

- `cause` states the failure in cohort-facing language, no jargon
  where avoidable, no traceback fragments. When an engine exception
  already carries a well-written message (e.g.
  `AmbiguousSnippetResolutionError`), that message IS the cause.
- `suggested_fix` is imperative and actionable ("Rename …", "Use
  forge_read_notes_in_vault to list …, then retry"). Never "an error
  occurred" / "contact support".
- `details` preserves everything an engineer needs: raw traceback,
  stdout, repr. It is never required reading for the cohort path.

## Rendering — plugin (Forge Output panel)

`renderForgeError` in `forge-error-core.ts`:

- `cause` renders first with the panel's error styling
  (`forge-output-error`), always visible.
- `suggested_fix` renders second, prefixed `Fix: `
  (`forge-output-message`), always visible.
- `details` renders inside a native `<details>` element
  (`forge-output-engineer-details`) whose `<summary>` reads
  `▸ Engineer details` — collapsed by default, browser-native toggle.
  No `details` → no disclosure element at all.

Only migrated error classes route through this renderer
(`classifyForgeError`); unmatched errors keep the legacy plain-text
`appendError` path (backwards compat).

## Rendering — forge-mcp (tool responses, `isError: true`)

`to_tool_response` in `error_response.py`:

```python
{
  "content": [
    {"type": "text", "text": "<cause>"},
    {"type": "text", "text": "<suggested_fix>"},
  ],
  "isError": True,
  "structuredContent": {
    ...tool OUTPUT_SCHEMA-required fields...,   # structured_base
    "cause": "...",
    "suggested_fix": "...",
    "details": "...",                            # only when present
  },
}
```

- `content` carries cause then fix as separate text items so
  text-only clients see both; `details` stays OUT of `content`.
- `structuredContent` MERGES the 3-shape alongside the tool's own
  OUTPUT_SCHEMA-required fields (every forge-mcp tool pins required
  keys clients already parse on error responses; replacing the
  payload wholesale would break them). Programmatic clients read
  `structuredContent.cause` / `.suggested_fix` / `.details`.

## Migration status

Migrated in the introducing drain (5 sites):

1. `AmbiguousSnippetResolutionError` (plugin classifier)
2. `SnippetExecError` (plugin classifier)
3. `SnippetResolutionError` / missing-chip (plugin classifier)
4. forge-transpile / engine service HTTP 5xx (plugin classifier
   status branch)
5. `forge_read_note` error branches (forge-mcp, via
   `to_tool_response`)

Everything else migrates incrementally: plugin classes are added to
`CLASS_RULES` in `forge-error-core.ts`; MCP tools swap their local
`_error` helper body for `to_tool_response(...)` with their
schema-required placeholder as `structured_base`. The prose-not-Recipe
rejection report (`appendLlmRecipeRejection`, 2026-07-17 drain)
predates this shape and already renders structured cause/fix/raw-output
content; it may be unified onto `renderForgeError` in a follow-up.
