# Slot Resolution — Wire-Up Survey

**Drain**: `2026-06-07-0100-slot-resolution-phase-1-design-pass`
**Stage**: §1.1 investigation (commit lands before §1.2 design).
**Status**: discovery; not implementation.

## Current state

E--, the Forge engine, the Forge plugin, and the Anticipated-extensions
clause of the constitution all promise `{{ ... }}` value-slot resolution.
Where the chain physically breaks today:

### E-- has slot-handling code but doesn't run it under Forge

`~/projects/e--/src/transpiler.py:34-46`:

```python
def _default_resolver(text: str) -> str:
    raise NotImplementedError(
        "LLM slot resolver not wired; pass resolve_slot=...")

def transpile(source: str, resolve_slot=None) -> str:
    """Transpile canonical E-- source to Python source text."""
    if resolve_slot is None:
        resolve_slot = _default_resolver
    tokens = tokenize(source)
    program = parse(tokens)
    return emit(program, resolve_slot)
```

`~/projects/e--/src/emitter.py:119-121` shows how a slot is handled in
the AST walker:

```python
if isinstance(node, LlmSlot):
    resolved = resolve_slot(node.text)
    return str(resolved)
```

The resolver's return value is spliced verbatim into the generated
Python source as a literal expression. The emitter doesn't do its own
validation — it trusts the resolver to return a parseable Python
expression. (E--'s reference resolver validates via `ast.parse(mode="eval")`
before returning; see below.)

`~/projects/e--/src/resolver.py:61-127` is the reference resolver
factory:

```python
def make_anthropic_resolver(cache_path: str = ".emm_cache.json",
                            model: str = _DEFAULT_MODEL,
                            client=None):
    state = {"client": client}

    def resolve(text: str) -> str:
        cache = _load_cache(cache_path)
        if text in cache:
            return cache[text]  # cache hit — no model call
        c = state["client"]
        if c is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise EmmResolveError(...)
            import anthropic
            c = anthropic.Anthropic(api_key=api_key)
            state["client"] = c
        try:
            response = c.messages.create(
                model=model, max_tokens=256, temperature=0,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
        except Exception as exc:
            ...
        raw = response.content[0].text
        expr = _strip_fences(raw)
        try:
            ast.parse(expr, mode="eval")  # validate only — never execute
        except SyntaxError:
            raise EmmResolveError(...)
        cache[text] = expr
        _write_cache(cache_path, cache)
        return expr
    return resolve
```

Notes on the reference resolver:

- **Cache shape**: JSON file mapping `slot_text → python_expr`. Single
  flat dict; not keyed by snippet, not keyed by surrounding context.
- **Cache lifecycle**: loaded fresh on every `resolve()` call; written
  on every miss. File I/O per call (acceptable at CLI scale; not at
  cohort scale).
- **Model**: `claude-haiku-4-5-20251001`, `temperature=0`, `max_tokens=256`.
- **System prompt**: `"Translate the English description into a single
  Python expression that evaluates to that value. Output ONLY the
  Python expression on one line — no prose, no markdown, no code fences."`
- **Output safety**: `ast.parse(mode="eval")` validates; the expression
  is NEVER executed at transpile time. (Spec §4.4.2 calls this out
  explicitly.)
- **Client construction**: lazy. Cache-only paths (cold cache hit) never
  touch the API key or the `anthropic` SDK.

### Forge's engine calls `transpile()` without a resolver

`~/projects/forge/forge/core/executor.py:486-505` (the canonical-form
compile path inside `resolve_action_code`):

```python
from forge.e_minus_minus import transpile, EmmSyntaxError
english = extract_section(snippet["body"], "English")
snippet_id = snippet.get("snippet_id", "<unknown>")
if english is None:
    raise ValueError(
        f"facet_form: canonical snippet '{snippet_id}' has no English heading")
try:
    transpiled = transpile(english.strip())   # ← no resolve_slot
except EmmSyntaxError as e:
    raise ValueError(...)
indented = "\n".join("    " + line for line in transpiled.split("\n"))
return f"def compute(context):\n{indented}"
```

`transpile(english.strip())` — no `resolve_slot=...` arg. E--'s
`_default_resolver` fires → `NotImplementedError`. A canonical snippet
containing a `{{ }}` slot would crash here at transpile time today.

In practice this hasn't surfaced because no bundled snippet authored
to date uses a `{{ }}` slot. (Canonical demo at
`~/projects/forge-moda/canonical_demo_compose.md` shipped in v0.2.68
and is slot-free.)

### Forge's existing hosted-LLM path is `/generate` only

`~/projects/forge/forge/core/llm.py:1-415` — implements
`generate_snippet_code()` and `canonicalize_python()`. Both call
`anthropic.Anthropic.messages.create(...)` directly (lines 305-311,
363-368). The engine code uses `_GENERATION_CACHE: dict[str, str]`
for in-memory caching; cache lives for the server process lifetime.

`~/projects/forge-client-obsidian/src/server.ts:187-211` — the plugin
calls the hosted endpoint via:

```typescript
export async function generateSnippetAlpha(
  serviceUrl: string,
  token: string,
  payload: AlphaGenerateRequest,
): Promise<GenerateResponse> {
  if (!token) {
    return { status: 0, json: { detail: 'Set your transpile token...' } };
  }
  const res = await requestUrl({
    url: `${serviceUrl}/generate`,
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    throw: false,
  });
  return { status: res.status, json: res.json };
}
```

So there's existing hosted-α plumbing: a `serviceUrl` (settings-stored),
a bearer token (settings-stored), the `requestUrl` Obsidian wrapper
for cross-origin fetch, and a `{status, json}` envelope contract. A
new `/resolve-slot` endpoint would land here as a sibling to `/generate`.

`~/projects/forge-client-obsidian/src/main.ts` references the `/generate`
flow at multiple points (lines 1438, 1453, 1468, 1487, 1527, 1555-1557,
1640) — the prompt's "low floor" gesture (Forge-click triggers
`/generate` → write Python back → run). A slot-resolution call would be
nested inside the `/generate` flow OR fire on first transpile of a
canonical snippet with slots.

## The conceptual gap

Three connection points are missing:

1. **Engine-side resolver injection.** `executor.py:493` needs to build
   a resolver and pass it as `transpile(english.strip(), resolve_slot=resolver)`.
   The resolver needs to:
   - Read the snippet's `# Slots` heading on load (analogous to how
     `extract_python` reads `# Python`).
   - On cache hit, return the cached expression without hitting the
     LLM.
   - On cache miss, call out to a hosted resolver endpoint OR call
     `make_anthropic_resolver()` directly (architectural choice; see
     below).
   - Write resolved values back to the snippet's `# Slots` heading on
     disk — but in V1 the engine runs in Pyodide which has no direct
     file system access; writes route through the plugin.

2. **Hosted `/resolve-slot` endpoint.** Today α only exposes `/health`
   + `/generate` (per `server.ts:39`). A `/resolve-slot` endpoint would
   land on the same host with the same auth pattern. Request/response
   shapes designed in §1.2 §A.

3. **Sidecar cache parsing + serialization.** A `# Slots` heading
   inside the snippet's `.md`, parallel to `# Python`. Engine reads it
   on snippet load; engine returns updated cache entries to the plugin
   which persists them. Helper goes in `forge/forge/core/slot_cache.py`
   (new file) — pure Python, no I/O.

## Architectural choice surface for Phase 2

### Option A — Reuse E--'s `make_anthropic_resolver` directly

The engine calls `make_anthropic_resolver(...)` (or wraps it) and the
resolver's lazy client construction picks up `ANTHROPIC_API_KEY` from
the engine process environment.

**Why rejected for V1:**

- V1 ships the engine in Pyodide running inside Obsidian (the client).
  There is no engine process environment to set `ANTHROPIC_API_KEY` in.
  The user would need to paste their API key into Forge settings, and
  the plugin would need to inject it into Pyodide's environment.
- Per the Mission preamble's "low floor" property, students must NOT
  see an API key or per-snippet LLM cost. Per-client API keys violate
  this directly.
- Even ignoring the credential-exposure issue: cohort scale (~20-30
  students hitting Anthropic from their local Pyodide instances) makes
  rate-limiting and cost-attribution unwieldy.
- The reference resolver's `.emm_cache.json` filesystem cache doesn't
  exist in Pyodide MEMFS at a useful path; cache writes wouldn't
  survive a session.

### Option B — New hosted `/resolve-slot` endpoint, plugin-mediated

The engine builds a resolver shim whose miss-path returns a marker
(or yields control to the plugin), the plugin calls
`${serviceUrl}/resolve-slot` with `Authorization: Bearer <token>`, the
server-side resolver wraps `make_anthropic_resolver()` (or a stateless
equivalent), returns `{python_expr, cache_key}`, and the plugin writes
the result back to the snippet's `# Slots` heading.

**Why chosen for V1:**

- Reuses the existing `/generate` plumbing (bearer-token auth, single
  shared service URL, no client-side API keys).
- Caching is per-snippet via the `# Slots` heading, which is committed
  with the snippet — diffable, frozen, identical across sessions.
- Pyodide isolation is preserved: the engine doesn't need filesystem
  write access; the plugin owns vault I/O.
- Symmetric with how `/generate` populates `# Python` — same write-back
  pattern.

The chosen option's seam between engine and plugin is the resolver's
return value. The cleanest shape that works in Pyodide:

- The engine resolver, on miss, **raises a specific exception** (call
  it `SlotCacheMiss(slot_text, cache_key)`) which bubbles through
  `transpile()` to `resolve_action_code` which surfaces it to the
  plugin via the standard `{status, json}` envelope.
- The plugin catches it, calls `/resolve-slot`, writes the result to
  the snippet's `# Slots` heading, retransports the snippet, and
  re-fires the transpile (now a cache hit).

Phase 2 will refine the seam (callback vs exception; per-snippet
batching of slot misses). For Phase 1 design purposes the resolver
factory's return shape is the helper the §1.3 tests exercise; the
engine-plugin boundary is described in §D of the design doc but not
extracted into a helper.

## Surprises

- **No `extract_slots` helper exists yet.** `extract_python`
  (`executor.py:508-529`) is the model — it scans body lines for a
  `# Python` heading, opens a `\`\`\`python` fence, collects until
  next heading. `extract_slots` will be near-identical for `# Slots`.
  Helper goes alongside in §1.3.

- **The cache key Q.** E--'s reference resolver keys by `slot_text`
  alone — same text across snippets shares a cached value. The
  design (§B) proposes `(snippet_id, slot_text)` keying so distinct
  snippets get distinct caches even when the slot text is the same.
  Trade-off: text-only is sharing-friendly; per-snippet is isolation-
  friendly. §F enumerates this as a risk.

- **Surrounding-context in the cache key.** The prompt anticipated this
  for disambiguation (`"a calm blue"` in a `plot(color=)` arg vs. in a
  `text` arg). Including it in the key tightens determinism but means
  any edit to the surrounding line invalidates the cache. §F lists
  this as a risk to balance in Phase 2.

- **Snippet-as-text vs snippet-as-AST for context.** The
  `surrounding_context` field would ideally be the parsed line
  containing the slot rather than the raw `node.text` E-- passes to
  the resolver. The emitter doesn't track line context today
  (`_emit_expr` sees just the `LlmSlot.text`). Phase 2 may need to
  extend the AST node to carry source coordinates, OR pass the entire
  English facet as context. The latter is simpler; the former is more
  surgical.

- **Caching at engine + cache at LLM**: E--'s reference resolver caches
  by `slot_text` in `.emm_cache.json`; Forge's `# Slots` cache will
  cache by `(snippet_id, slot_text)` per-snippet. These are different
  scopes. The hosted resolver itself could cache too (server-side
  shared cache to amortize "tomato color" across 30 students), but
  that's a Phase 2+ optimization. The per-snippet `# Slots` cache is
  load-bearing for V1.

- **Failure mode at runtime.** E--'s spec §1.2 forbids runtime LLM
  calls. If a snippet's `# Slots` heading is missing an entry the
  English facet references, the engine MUST raise rather than fall
  back to a live LLM call. Phase 2's resolver returns NULL / raises
  on cache miss; the plugin sees this in the transpile error envelope
  and triggers `/resolve-slot` from the surrounding context (Forge-
  click → /generate → transpile → cache miss → /resolve-slot → write
  back → retry transpile). The semantically clean shape is "all slots
  resolved at /generate time, runtime never sees a miss."

## Next steps (Phase 1)

1. §1.2 design commit (`slot-resolution-design.md`).
2. §1.3 pure-core helpers (`slot_cache.py`, `slot-resolver-factory-core.ts`)
   with full test coverage.
3. §1.4 constitution clause B7.3 (DRAFT).
4. §5 feedback + user review surface (§8 numbered decisions).

## Cited files

| File | Lines | What it shows |
|---|---|---|
| `e--/src/transpiler.py` | 34-46 | `_default_resolver` + transpile() signature |
| `e--/src/resolver.py` | 61-127 | reference Anthropic resolver factory |
| `e--/src/emitter.py` | 119-121 | how the resolver's return value is spliced |
| `e--/docs/spec.md` | §1.2, §4.4 | LLM-only-at-transpile-time HARD RULE + slot semantics |
| `forge/forge/core/executor.py` | 486-505 | `resolve_action_code` calling `transpile()` without resolver |
| `forge/forge/core/executor.py` | 508-529 | `extract_python` — model for `extract_slots` helper |
| `forge/forge/core/llm.py` | 1-415 | existing `/generate` engine-side implementation |
| `forge-client-obsidian/src/server.ts` | 187-211 | `generateSnippetAlpha` — hosted-endpoint plumbing pattern |
| `forge-client-obsidian/src/main.ts` | 1468-1600 | plugin-side generate orchestration |
| `forge/docs/specs/constitution.md` | 47-57 | Mission preamble naming canonical form + slot resolution |
| `forge/docs/specs/constitution.md` | 356-400 | B7.1 canonical call syntax |
| `forge/docs/specs/constitution.md` | 780-791 | Anticipated extensions: slot resolution as Phase 2 |
