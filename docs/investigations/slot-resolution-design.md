# Slot Resolution — Design

**Drain**: `2026-06-07-0100-slot-resolution-phase-1-design-pass`
**Stage**: §1.2 design commit (follows §1.1 investigation, precedes §1.3 helpers).
**Status**: design pending review. NOT shipped.

Read `docs/investigations/slot-resolution-wire-up.md` first for the
state-of-the-world findings this design follows from.

## §A — Hosted `/resolve-slot` endpoint

A new endpoint on the same hosted-α service that today exposes
`/health` and `/generate`. Same bearer-token auth, same `requestUrl`
plumbing in the plugin, same `{status, json}` envelope.

### Request

```jsonc
POST /resolve-slot
Authorization: Bearer <transpileServiceToken>
Content-Type: application/json

{
  "slot_text": "the first prime number greater than 5",
  "snippet_id": "forge-moda/fib_demo",
  "surrounding_context": "Set result to [[fibonacci]]({{the first prime number greater than 5}}).",
  "domain_hints": ["moda"]
}
```

Fields:

- **`slot_text`** (required, string). The free English inside the
  `{{ ... }}` markers, verbatim, no normalization. This is the primary
  cache key contributor.
- **`snippet_id`** (required, string). Forge's bare-or-qualified
  snippet ID. Lets the resolver scope distinct slots that happen to
  share text across snippets, and lets server-side logging attribute
  resolutions to authors.
- **`surrounding_context`** (required, string). The full English line
  (or short window) containing the slot. Disambiguates `"a calm blue"`
  in `[[plot]](data, color={{a calm blue}})` vs. `Set name to
  "{{a calm blue}}".` The LLM prompt receives this context to ground
  the resolution.
- **`domain_hints`** (optional, array of string). Mirrors the
  `active_domains` field on `/generate` (per `forge/core/llm.py:24`).
  Lets the resolver pull domain-specific prompt fragments — e.g., moda's
  diffusion vocabulary — to steer `"a calm blue"` toward a value
  consistent with the bundled palette.

### Response

```jsonc
HTTP/200 OK
Content-Type: application/json

{
  "python_expr": "7",
  "cache_key": "abc123def456..."  // hex sha256
}
```

Fields:

- **`python_expr`** (string). A single-line Python expression that the
  emitter splices verbatim into generated Python. Validated server-
  side via `ast.parse(mode="eval")` before return — invalid responses
  surface as HTTP 502.
- **`cache_key`** (string, hex sha256). Computed server-side from
  `compute_slot_cache_key(slot_text, snippet_id, surrounding_context)`.
  The plugin uses this as the dict key when writing to the snippet's
  `# Slots` heading. Server and client compute the SAME key from the
  SAME inputs (the deterministic helper in §1.3 lives in both code-
  bases — Python on the engine, TypeScript on the plugin).

### Errors

- **400 Bad Request**: malformed JSON, missing required field, fields
  exceed reasonable length limits (slot_text > 1KB, surrounding_context
  > 8KB). `{"detail": "<message>"}` envelope, matching `/generate`.
- **401 Unauthorized**: missing or invalid bearer token. Same shape as
  `/generate`.
- **429 Too Many Requests**: rate-limit ceiling hit. `Retry-After`
  header optional. Phase 2 may add cohort-wide bucketing.
- **502 Bad Gateway**: LLM returned a non-parseable Python expression
  OR the LLM call itself failed. `{"detail": "<message>"}`. Client
  retries are NOT automatic — the user sees a Notice and can re-fire
  the gesture.
- **5xx other**: server-internal failure. `{"detail": "<message>"}`.

### Determinism contract

Same `(slot_text, snippet_id, surrounding_context, domain_hints)`
MUST yield the same `python_expr` deterministically. The server-side
LLM call uses `temperature=0` (matching E--'s reference resolver) and
a system prompt designed for stable, single-expression output. Same
contract as E-- spec §4.4.2.

A separate **server-side cache** keyed on the same tuple amortizes
"common" slot text across cohort members — first author resolves
"a calm blue" once, downstream students hit the warm cache. Cache TTL
is server-side policy, not part of the contract.

### Rejected alternative

Reusing E--'s `make_anthropic_resolver()` directly inside the engine.
Rejected for V1 because:

1. Pyodide-hosted engine has no `ANTHROPIC_API_KEY` and shouldn't —
   the Mission's "low floor" property forbids per-client API keys.
2. The plugin would need to inject the key into Pyodide environment,
   which exposes the key in browser DevTools and reaches every cohort
   member's local storage.
3. Per-student Anthropic accounts don't fit the closed-beta cohort
   model.
4. The reference resolver's `.emm_cache.json` doesn't fit Pyodide's
   MEMFS isolation. The `# Slots` sidecar gives us per-snippet, vault-
   resident caching that survives sessions and is reviewable in git.

## §B — Cache shape

### Sidecar `# Slots` heading

Each snippet that contains `{{ }}` slots in its English facet gains a
new top-level heading `# Slots` (parallel to `# English`, `# Python`,
`# Dependencies`). The heading contains a YAML-encoded dict mapping
cache keys to Python expressions:

```markdown
# Slots

```yaml
slots:
  "a3f5c8...": "7"
  "b2e6d1...": "\"#3366cc\""
  "c9k4l2...": "[1901, 1907, 1913, 1931, 1933, 1949, 1951, 1973, 1979, 1987, 1993, 1997, 1999]"
```
```

### Why YAML

- Already-vaulted snippets use YAML frontmatter for `inputs`,
  `description`, etc. (`forge/core/registry.py` parses YAML
  frontmatter). The dependency on `pyyaml` is already in the engine.
- Quotes-around-keys are needed because cache keys are arbitrary hex
  strings; YAML's bare-key rules don't handle that cleanly.
- Quotes-around-values are needed because Python expressions can
  contain `:` and other YAML metacharacters.
- A `slots:` wrapper makes the YAML self-describing if the parser
  encounters extra top-level keys in the future.

### Cache key

The key is `compute_slot_cache_key(slot_text, snippet_id, surrounding_context)`
— hex-encoded sha256 of the tuple. Specified in §1.3 helper 1.

`surrounding_context` is the rendered English line containing the slot,
trimmed of leading/trailing whitespace. Adding it as a key contributor
means an edit to the surrounding line invalidates the slot's cache —
the right behavior, because the line's other tokens affect disambiguation.

### Why sidecar instead of inline rewrite

- **Non-mutating English facet**: the canonical `# English` heading
  stays readable as authored. `{{ ... }}` slots persist as English
  for source-of-truth diffability.
- **Mirrors `# Python`'s post-generate write pattern**: B5/B6 already
  cover the same shape — English is authored, Python is system-
  maintained sidecar.
- **Diff-friendly**: a new slot adds a single YAML line. Editing one
  slot's text adds one line, removes one line (the cache entry under
  the old key). No churn on the English facet.
- **User-overridable**: a learner can hand-edit a Python expression
  directly in the `# Slots` heading to override the LLM's choice. The
  "Slots cache *is* the freeze" property (per E-- spec §4.4.1) gives
  the override automatic effect — next transpile is a cache hit.

### Why include `# Slots` even when empty?

We don't. Snippets with no slots have no `# Slots` heading. The
`parse_slots_section` helper returns `{}` for missing heading, missing
section, or empty YAML. This is consistent with `extract_python`'s
behavior on snippets without a Python facet.

## §C — Resolver factory

Two parallel helpers — Python for the engine side, TypeScript for the
plugin side. Both compute the same cache key for the same inputs
(verified by §1.3 tests covering deterministic hashing).

### Python (engine side) — `forge/forge/core/slot_cache.py`

```python
def make_forge_slot_resolver(
    snippet_id: str,
    slot_cache: dict[str, str],
    hosted_resolve_slot,  # callable: (req) -> awaitable response
):
    """Build a `resolve(text) -> str` callable that pipes through
    Forge's hosted /resolve-slot endpoint with per-snippet caching."""
    def resolve(text: str) -> str:
        # Cache check first (deterministic, no network).
        key = compute_slot_cache_key(text, snippet_id, surrounding_context="")
        if key in slot_cache:
            return slot_cache[key]
        # Cache miss — hosted call.
        req = SlotRequest(slot_text=text, snippet_id=snippet_id, ...)
        resp = hosted_resolve_slot(req)
        slot_cache[key] = resp.python_expr  # populate for next time
        return resp.python_expr
    return resolve
```

Phase 1 ships only the helpers + tests — the resolver factory itself
is NOT wired into `executor.py`. Phase 2 will replace the bare
`transpile(english.strip())` at `executor.py:493` with one that
constructs the resolver from a parsed `# Slots` heading + a callable
that surfaces cache-misses to the plugin via the standard error
envelope.

### TypeScript (plugin side) — `src/slot-resolver-factory-core.ts`

Mirror shape. Used by the plugin's transpile-orchestration path
(Phase 2) when the slot-cache lives in the vault and the hosted-call
hits `/resolve-slot`:

```typescript
export function makeForgeSlotResolver(
  snippet_id: string,
  slot_cache: Record<string, string>,
  hosted_resolve_slot: HostedResolveSlot,
): (slot_text: string) => Promise<string>;
```

Tests at `src/slot-resolver-factory-core.test.ts` cover cache-hit,
cache-miss, mutation side-effect, snippet isolation, error
propagation, hashing stability, idempotence. See §1.3 below.

## §D — Integration points

Three connection points in the engine-plugin call graph. Phase 2 wires
these; Phase 1 just specifies them.

1. **Engine-side cache read** (`forge/core/executor.py`, near line 487).
   When `resolve_action_code` enters the canonical-form branch, the
   snippet body is passed through a new `extract_slots(body)` helper
   that returns the parsed `# Slots` dict (or `{}`). The dict is
   passed into the resolver factory.

2. **Engine resolver-build + transpile-call**. The resolver factory
   returns a callable that the engine passes to E--'s
   `transpile(source, resolve_slot=resolver)`. The factory CLOSES OVER
   the cache dict (mutable) so that resolved values populate it
   immediately. The engine does NOT mutate the snippet file directly
   — it returns the updated cache as part of the transpile result so
   the plugin can write it.

3. **Cache writes** (plugin-side). When the engine surfaces a transpile
   result that includes new cache entries, the plugin writes them back
   to the snippet's `# Slots` heading via the vault adapter
   (`adapter.process(file, content → newContent)`). The write is
   atomic and goes through Obsidian's modify-event pipeline so the
   editor reflects the new heading.

### Engine-side write vs. plugin-side write (option choice)

The prompt's §D names two choices. **Chosen: option (ii), plugin-side
write.** Reasons:

- Pyodide's MEMFS is shimmed against the vault but writes don't
  automatically persist to disk on each call — the engine needs a
  Pyodide-to-vault sync hook that today only fires for `# Python`
  via the post-/generate write path (`main.ts:writeGeneratedCode`).
  Reusing that pattern means the plugin already owns this surface.
- Symmetric with how `/generate` populates `# Python`: the engine
  returns generated code as data, the plugin writes it. Symmetry
  reduces engine surface area.
- The engine running in Pyodide treats the vault filesystem as
  read-only conceptually; making `# Slots` a system-written sidecar
  reinforces this invariant.

The trade-off is plumbing complexity — the engine's transpile-result
shape grows a `slots_cache_updates: dict[str, str]` field that the
plugin merges into the existing `# Slots` heading. Phase 2 spec covers
the result envelope.

### Cache-miss surfacing seam

How does the engine signal "I need slot resolution to continue"?

**Chosen shape (Phase 1 spec; Phase 2 implements)**: the engine
resolver is async by signature, but in Pyodide async-from-Python-into-
JavaScript requires the iframe's existing JS host bridge. For V1 the
simpler shape is:

1. Engine builds the resolver with the cache dict pre-populated from
   the snippet's `# Slots` heading.
2. On miss, the resolver **raises** `SlotCacheMiss(slot_text,
   snippet_id, surrounding_context, cache_key)`. This propagates
   through `emit()` → `transpile()` → `resolve_action_code` and
   surfaces in the standard `{status: 400-ish, json: {missing_slots:
   [...]}}` envelope.
3. The plugin catches the missing-slots envelope, fires
   `/resolve-slot` for each (batched into one request payload), writes
   the results back to `# Slots`, and re-fires the original gesture
   (Forge-click → /generate → transpile → now a cache hit).

The two-pass shape preserves E-- spec §1.2 (no runtime LLM) at the
cost of one round-trip on first-transpile of a slot-bearing snippet.
Subsequent transpiles are cache hits and complete in one pass.

Phase 2 may explore an async resolver shape if the two-pass round-trip
shows up as user-visible latency. For V1, the two-pass is fine.

## §E — Constitution clause B7.3 draft

To land in `forge/docs/specs/constitution.md` after B7.2 (line ~428).
Marked DRAFT until Phase 2 implementation lands.

> **B7.3.** *Value-slot resolution.* **[DRAFT — pending Phase 2
> implementation of slot resolution; see
> investigations/slot-resolution-design.md]**
>
> When a snippet's canonical E-- facet contains a `{{ free-text }}`
> value slot, the engine resolves the slot to a Python expression at
> **transpile time** via a Forge-hosted `/resolve-slot` endpoint
> (parallel to the existing `/generate` endpoint, same bearer-token
> auth). The resolved expression is cached per
> `(snippet_id, slot_text, surrounding_context)` triple in the
> snippet's `# Slots` heading; the cache is the freeze mechanism.
>
> **At runtime, the engine MUST NOT hit the LLM.** If the cache is
> missing a slot at runtime (the snippet was authored after the cache
> was generated, or the cache was hand-deleted), the runtime raises
> an error; the user re-fires the authoring gesture to re-populate
> the cache. Per E-- spec §1.2, LLM calls are transpile-time only —
> this is a HARD RULE.
>
> The resolver is hosted-side responsibility: the engine sees only
> the resolved Python expression, never the LLM. The plugin owns the
> `# Slots` write-back: when a cache-miss surfaces from transpile,
> the plugin calls `/resolve-slot`, writes the result to the
> snippet's `# Slots` heading, and re-fires the original gesture.
>
> Per the Mission's "low floor" property, students never see an API
> key or per-snippet LLM cost; per the "high ceiling" property,
> hand-editing a cached value in `# Slots` to override the LLM's
> choice is supported.
>
> Slot text MUST be stable across cache hits — the cache key
> incorporates the slot text exactly as authored, plus the
> snippet_id and the surrounding English line for disambiguation. A
> user editing the slot text invalidates that slot's cache entry
> (new hash key) and triggers re-resolution at next transpile.
>
> The `# Slots` heading is a YAML-encoded dict of `cache_key →
> python_expr`. See `docs/investigations/slot-resolution-design.md`
> §B for the wire-format.

## §F — Risks for Phase 2

| Risk | Mitigation in design | Open question for Phase 2 |
|---|---|---|
| Determinism: LLM responses must be stable per (slot_text, snippet_id, surrounding_context, domain_hints) | `temperature=0`, single-expression system prompt, server-side cache amortizes "common" slots | Validate empirically that the same tuple yields the same expression across 100 calls. Risk if Anthropic models drift mid-cohort. |
| Cache key sensitivity: choosing the right key contributors | Phase 1 design picks (slot_text, snippet_id, surrounding_context). The surrounding_context contribution invalidates the cache on line edits — intended. | Should `domain_hints` be in the key too? Pro: distinct vaults get distinct caches. Con: changes to active domains invalidate every slot in every snippet. Phase 2 calls. |
| Runtime LLM violation: cache miss at compute time | Engine raises `SlotCacheMiss`; the plugin catches, calls `/resolve-slot`, retries. Two-pass cost only on first transpile of a slot-bearing snippet. | Worth instrumenting in Phase 2 to confirm the round-trip doesn't visibly stall the Forge-click feel. If it does, a synchronous-Pyodide bridge to `/resolve-slot` becomes necessary. |
| Migration: existing slot-free snippets work unchanged | `parse_slots_section({})` returns `{}` for missing `# Slots` heading. Resolver short-circuits — no calls. | None. |
| API cost / rate limiting: cohort scale on first-tweak experience | Server-side cache amortizes cross-cohort. Hosted-α can apply per-token rate limits matching the existing `/generate` policy. | What's the cost ceiling per student per cohort? Should the hosted service ship a `cost-so-far.json` per token? |
| Slot text in commit diff: invalidated cache rows leave detritus | Phase 2 implementation choice: auto-prune cache rows whose `cache_key` doesn't match any current slot in `# English`. | Decide whether to prune (clean diffs) or retain (history). Pruning is easier; retention is more diff-noisy but informative. |
| Surrounding-context extraction: where exactly in the English line is "surrounding"? | Design specifies "the rendered English line containing the slot, trimmed of leading/trailing whitespace." | E--'s emitter doesn't track line context at the AST level. Phase 2 either extends `LlmSlot` to carry source coordinates OR the engine passes the whole English facet as context and lets the resolver server slice it. |
| Hosted endpoint availability: the closed beta's α might be down when a student tries to author with a slot | Surface a clear Notice: "Forge slot resolver unavailable; try again, or hand-edit the # Slots heading." | Phase 2 adds a `/health` check before `/resolve-slot` calls, surfaces a degraded-mode banner. |

## §G — Summary of architectural choices made in Phase 1

1. **New hosted `/resolve-slot` endpoint**, parallel to `/generate`. Not
   direct `make_anthropic_resolver()` in the engine.
2. **Sidecar `# Slots` YAML heading**, not inline rewrite of `# English`.
3. **Plugin-side cache write** (option ii in prompt §D), engine returns
   cache updates as data.
4. **Two-pass cache-miss seam**: engine raises `SlotCacheMiss`, plugin
   handles round-trip, retries transpile. Preserves E-- spec §1.2 (no
   runtime LLM).
5. **Cache key**: `sha256(slot_text || \\x00 || snippet_id || \\x00 ||
   surrounding_context)`. Snippet-scoped, context-aware.
6. **Validation**: server-side `ast.parse(mode="eval")` on
   `python_expr` before return. Mirrors E-- reference resolver's
   safety check.

All six are open to refinement by user review before Phase 2 starts.
The §1.3 helpers ship the cache-shape + hashing + factory shape; if
user review revises one of these, the helpers refactor narrowly.
