# V2 architectural direction

**Status**: forward-looking commitment, drafted 2026-06-07 from a multi-turn brainstorm between forge-core and the driver. Not yet shipped; V1 closed-beta is the current ship target. This doc captures the V2 direction so the conclusion survives across sessions and informs future drains.

**Companion docs**: `specs/constitution.md` (current V1 contract), `specs/chips-schema.md`, `specs/v2-EPython.md` (forthcoming spec for the EPython language).

## TL;DR

V2 reframes Forge's language and facet model around two commitments:

1. **EPython** = Python + slots + Forge snippet calls. The snippet's executable form is real Python plus exactly two syntactic extensions: `[[snippet]](args)` for inter-snippet calls and `{{free-text}}` for LLM-fill value slots in expression positions. Everything else is standard Python.

2. **Two-facet snippet model**: each snippet has an English-source facet (free prose) and an EPython facet, with a `source` field designating which is authoritative. The other is a derived view. Expanding a facet in the editor IS the gesture that promotes it to source.

E-- as a separate language retires. Existing V1 canonical-E-- snippets migrate to EPython via LLM normalization on first open under V2.

## EPython definition

EPython is **Python with two extensions** and nothing else.

### Extension 1: Snippet call syntax

```
[[snippet_name]](args)
```

Mandatory parens, even for zero-arg snippets (`[[wake]]()`). The wikilink syntax is statically extractable (chip palette, freeze affordance, graph view all consume it without AST walking) and visually distinguishes snippet calls from builtin / domain function calls.

Disambiguation rule against Python nested lists: **`[[name]]` is a snippet call iff it's immediately followed by `(`**. Otherwise standard Python (a list containing a list). The trailing `(` is the unambiguous signal.

Examples:
- `[[wake]]()` — snippet call, zero args
- `[[chorus]](bars=4)` — snippet call with keyword arg
- `[[print]]("hi")` — snippet call (if `print` is treated as a snippet; in practice `print` is a Python builtin so this would be `print("hi")` in EPython)
- `[[1, 2], [3, 4]]` — Python list of two lists
- `[[a, b]]` — Python list of single inner list

At compile time, snippet calls rewrite to either `context.compute('snippet_name', args)` or to a namespace shim lookup per the v0.2.68 Stage 2.5 namespace injection. Both routes route through the SnippetRegistry resolver.

### Extension 2: Value slots

```
{{free-text describing the desired value}}
```

Slots are valid in any Python expression position. The text inside is fuzzy intent the LLM commits to a Python expression at compile time. Resolution is cached per `(slot_text, snippet_id)` hash; freeze-by-cache semantics per the existing B7.3 contract.

Examples of valid slot positions:
- `greeting = {{a friendly hello in storybook style}}`
- `colors = [{{a calm blue}}, {{a warm red}}]`
- `score = with_velocity(score, profile={{a soft fade}})`
- `for fruit in {{a list of five tropical fruits}}: print(fruit)`

Slot resolution happens at compile time only (E-- spec §1.2 HARD RULE: LLM never in runtime path). The resolved Python expression is persisted as part of the compiled output, cached, invalidated when slot text changes.

**Edge cases**:
- Inside string literals: `f"hello {{world}}"` is Python's escaped-brace syntax (renders `{world}`), NOT a slot. Slots only outside string literals.
- Inside comments: `# {{this is text}}` is comment text, not a slot.
- Nested slots `{{outer {{inner}}}}` are not supported (lex error).

### What EPython is NOT

EPython is NOT E--. There are no E-- keywords (`Set`, `Do`, `Give back`, `Define`, `If` as a leading keyword, etc.). There is no E-- terminator (`.`). There is no operator sugar (`minus`, `times`, `modulo`). There is no closed vocabulary.

The early-V1 architectural exploration around E-- as a structured-English canonical form does not persist into V2. The brainstorm validating EPython concluded that the closed-vocabulary tax (every Python operator needing an E-- equivalent, attribute access syntax, record-update syntax, etc.) didn't scale to real domain snippets, and the aesthetic was not load-bearing for the adult audience Forge actually serves.

E-- the language retires at the V2 boundary. The vendored `forge/forge/e_minus_minus/` package's transpiler is no longer needed; the package becomes the pre-processor + parser-extension layer for the two EPython markers.

## The two-facet snippet model

Each snippet has two facets:

### English source

```markdown
# English

Greet the user by name. Use a warm storybook tone — something like "hello, [name], welcome..."

The greeting should adapt to {{the time of day}}.
```

Free prose. The author writes in natural language. May contain slots (`{{}}`) for fuzzy values the author wants the LLM to commit on.

When `source: english`, the LLM normalizer translates English-source into EPython at save time (or on first compute, cached thereafter). The normalization is a one-shot LLM call producing valid EPython with snippet calls and slots preserved as markers.

### EPython

```python
def compute(context, name):
    time_of_day = {{the time of day}}
    greeting = f"hello, {name}, welcome at {time_of_day}!"
    print(greeting)
    [[log_greeting]](greeting)
```

Real Python with the two extensions. Edited directly by the author when `source: epython`.

### The source field

```yaml
---
type: action
source: english   # or epython
---
```

The `source` field designates which facet is authoritative. The other is a derived view:

- `source: english` → English facet is edited; EPython facet is auto-derived (LLM normalization).
- `source: epython` → EPython facet is edited; English facet is auto-derived (LLM summary) or empty / docstring-only.

The non-source facet is read-only in the editor. Reading mode (Obsidian's view mode) shows all facets for inspection regardless of source designation.

### Gestural promote workflow

The editor at any time shows ONE expanded facet — the source. The other is collapsed. Switching source is the gesture of expanding the other facet:

1. Author expands the currently-derived facet (e.g., expands EPython while in source: english).
2. The expand gesture commits the currently-derived content as authoritative.
3. The `source` field updates to reflect the new source designation.
4. The previously-source facet collapses; its content becomes derived (regenerated on next save / compute).

This is the "promote workflow" without a button — the visual state IS the architectural state. The author's gesture has semantic meaning: "make this my authoring surface from now on."

**Direction of promotion**:
- **Downward** (English → EPython): clean. Each step refines / adds detail. Author "outgrew" English source for this snippet.
- **Upward** (EPython → English): fuzzy. LLM has to summarize / abstract from concrete code. The system warns: "the derived English may not exactly match your EPython behavior — review before saving."

Most students will only go downward. The gestural model supports both, asymmetrically priced.

## What V1 ships vs V2 changes

| Concern | V1 (current) | V2 |
|---|---|---|
| Source-of-truth English form | E-- canonical (`Set x to ...`, `Do <call>.`, etc.) | EPython (Python + 2 markers) |
| Source-of-truth Python form | Cached transpile output from E-- | Equivalent to source when source: epython |
| `facet_form` field | `canonical` or absent | Retired; replaced by `source` field |
| `edit_mode: python` | Override gesture for canonical snippets | Subsumed by `source: epython` |
| Free-English snippets | LLM-generated `# Python` via `/generate` | LLM-normalized to EPython via `/normalize` |
| Snippet call syntax | `[[name]](args)` in E-- canonical | `[[name]](args)` in EPython (unchanged) |
| Slot syntax | `{{free-text}}` in E-- canonical | `{{free-text}}` in EPython (unchanged) |
| Engine compile path | E-- transpile + slot resolution → Python | Pre-process slot resolution + snippet-call rewriting → Python |
| Chip palette emit form | `Do [[snippet]](<arg>).` (E-- canonical) | `[[snippet]](<arg>)` or `snippet(<arg>)` (EPython call form) |

V1 closed-beta ships the current state. V2 reframes incrementally — engine + plugin + tutorial restructure — with backward compatibility for migration.

## Migration path

V1 canonical-E-- snippets need to be normalized to EPython under V2:

- `Set x to 5.` → `x = 5`
- `Do [[print]]("hi").` → `print("hi")` (builtin) or `[[print]]("hi")` (if print is treated as a snippet — unlikely)
- `If x is less than 0: ... Set x to 0.` → `if x < 0: x = 0`
- `Give back x.` → `return x`
- `[[snippet]](args)` → `[[snippet]](args)` (preserved verbatim)
- `{{slot text}}` → `{{slot text}}` (preserved verbatim)
- E-- comparison operators (`is less than`, `equals`, etc.) → Python operators (`<`, `==`, etc.)

The migration is mostly mechanical and can be performed by an LLM pass per snippet. V2 ship would include a one-time migration drain converting all bundled E-- canonical snippets to EPython; user-vault canonical snippets get migrated on first open under V2 (with backup to `<snippet>.bak.v1.md` preserving the E-- original).

Free-English V1 snippets (no `facet_form: canonical`) become EPython on first compute under V2: the existing `/generate` call is replaced by `/normalize` producing EPython, and `# Python` is the cache (same shape as B7.3).

## Why this direction

The brainstorm trajectory that led here is worth preserving as rationale:

1. **Multi-facet coherence is hard**. The session-long slot resolution arc surfaced multiple bugs related to facet-vs-cache-vs-registry routing. Reducing the number of architectural layers reduces the surface area for similar bugs.

2. **Single source of truth per snippet** eliminates drift between facets. The `source` field commits unambiguously to which facet is editable; others are derived.

3. **E--'s aesthetic value didn't scale**. The bounce_off_walls example reads beautifully in E--; the dispersing music snippet requires data literals (`[(0.0, 0.85), (3.5, 0.6), ...]`) and list comprehensions that E--'s closed vocabulary doesn't cover. Forcing real domain snippets through E-- means either expanding the language (it becomes Python with different syntax) or wrapping everything non-trivial in `[[builtin]]()` calls (a tax with no payoff for adults).

4. **English-to-canonical is code generation, not translation**. The LLM normalizer commits to specific implementations the English left underspecified. Generating to Python (the target the snippet will execute anyway) is more honest than generating to an intermediate canonical English language.

5. **The audience is adults, not children**. Adults can handle Python's syntactic surface. The "low floor" property is served by the English-source facet (free prose authoring) not by an English-flavored IR.

6. **Theory A constructionism is preserved**. Authors make artifacts in a medium that lets them tinker. The medium is English (for those who prefer prose) or Python (for those who prefer code). The slot magic is the headline constructionist feature; it lives in EPython where it works naturally.

7. **Portability is a side effect, not a goal**. Students who learn EPython have learned Python with two markers. When they leave Forge, the Python part transfers. The two markers are Forge-specific but small enough to set aside.

## Deferred decisions / open questions

Some details are V2-spec-level and don't need resolution before commitment:

- **`source: epython` vs `source: python`**: do we offer a "pure Python, no slot extensions" source mode for users who want their snippets to be standard Python? Probably no — EPython's two extensions are inert when not used, so `source: epython` covers the pure-Python case.

- **Name**: "EPython" or just "Python"? The Python community's `python` brand has cachet; "EPython" suggests "Forge's variant." Tutorial-facing name might be "Python" with the spec calling it "EPython" technically. Decision deferred until tutorial restructure.

- **Chip palette emit form**: `[[snippet]](<arg>)` vs `snippet(<arg>)`. The first is explicit and Obsidian-friendly; the second is cleaner Python. Probably `[[]]` form by default with the disambiguation rule, since the audience using chips benefits from the graph-view + freeze affordance the wikilinks enable.

- **English source mode persistence**: do most authors stay in English source mode permanently, or is it primarily a draft surface they leave? Empirical question for V1 closed-beta cohort observation. If permanent, English source needs polish; if draft surface, less investment.

- **Migration mechanics for slot-bearing snippets**: V1 slot resolution caches in `# Python` heading per B7.3. V2 keeps the same shape but in EPython source. Migration just renames `# Python` to `# Forge Python` or leaves it alone — cosmetic.

- **E-- rendering as a read-only view layer**: considered as a way to preserve the E-- aesthetic without architectural cost. Decided against — added implementation burden, mixed-form rendering can be visually choppy, "source of truth is source of truth" principle won out.

## Implementation effort estimate

Scoped at the V2 boundary:

| Component | Effort | Notes |
|---|---|---|
| EPython pre-processor (slot resolution + wikilink call rewriting) | 1 week | Mostly reuses v0.2.72+ slot machinery |
| English → EPython normalizer (LLM endpoint) | 3 days | New `/normalize` hosted endpoint paralleling `/generate` |
| Plugin chip palette + modal updates | 3 days | Emit EPython call syntax; `source` field replaces `facet_form` |
| Tutorial restructure (forge-doc Tier 1) | 1 week | Rewrite chapters 1-9 for Python + 2 markers |
| Constitution rewrite (B7.1, B7.3, B8) | 2 days | Update for EPython contract; retire E-- references |
| One-shot bundled-vault migration | 3 days | LLM pass converting forge-moda + forge-tutorial canonical snippets |
| User-vault migration tooling (on first open under V2) | 3 days | LLM pass with backup-to-`.bak.v1.md` |
| Tests + integration verification | 1 week | Cross-facet, normalization, slot resolution, migration |

**Total**: ~4 weeks engineering + 1 week tutorial restructure. Bounded V2 scope.

## What V2 retires

- E-- as a separate language (the vendored package's transpiler is no longer needed)
- `facet_form` field (replaced by `source`)
- `edit_mode: python` (subsumed by `source: epython`)
- Two-pipeline compile (free-English `/generate` vs canonical E-- transpile — both unify under EPython)

What survives unchanged:

- Two markers (`[[]]` and `{{}}`)
- Slot resolution machinery (B7.3 cache shape, /resolve-slot endpoint)
- Constitution Mission preamble + S-series + A-series
- B7.2 builtin interception (Python builtins remain auto-handled)
- B8 edit_mode concept (relabeled as `source`)
- All chip palette / freeze affordance / graph view machinery (consumes `[[]]` markers; works identically over EPython)

## Cross-references

- Current constitution: `specs/constitution.md`
- Slot resolution contract: B7.3 (current; will be amended for EPython at V2 ship)
- Chip schema: `specs/chips-schema.md`
- E-- standalone spec (deprecated under V2): `~/projects/e--/docs/spec.md`
- Stage 2.5 sibling-snippet namespace injection: forge engine `executor.py:_build_snippet_shims` (preserved unchanged for EPython snippet calls)
- v0.2.72 unified `# Python` cache: B7.3 amendment 2026-06-07 (`cache only when cache pays for itself`)
- v0.2.75 SnippetRegistry refresh routing fix (cross-cutting "AUTHORING default" pattern)

## Hold for evidence

This is a forward-looking commitment, not a ship plan. V2 work begins after:

1. V1 closed-beta ships and stabilizes (slot arc + Tier 1 + polish + mint-laptop smoke all green; cohort uses it).
2. Cohort data accrues on V1 use patterns — do students stay in canonical authoring? Do they flip to `edit_mode: python` often? Do free-English snippets dominate or are they rare?
3. The data either validates the V2 direction (low-floor English authoring + Python IR is what users actually want) or surfaces friction that reshapes the commitment.

Either way, V2 work is bounded and well-specified by the time it starts. The brainstorm output captured here is the architectural commitment; the timing is downstream of V1 evidence.

## Revision history

- 2026-06-07: initial draft from forge-core + driver brainstorm (this document).
