# `_chips.md` schema — v2 (current) + v3 (authorized 2026-06-06)

**Status v2:** committed 2026-06-04; adopted in plugin code via v0.2.48 + polish v0.2.49–v0.2.54.

**Status v3:** authorized 2026-06-06. Awaiting CC drain to adopt in the chip-palette code path. Adds two capabilities forge-doc's tutorial work surfaced as needed: per-chapter `_chips.md` walk-up discovery, and synthetic chips declared directly in `_chips.md` with no backing snippet file.

This document specifies the v2 schema (currently shipped in the chip palette) and the v3 extensions (authorized, not yet implemented). v1 was the vault-explicit-only shape (every chip hand-authored in `_chips.md`). v2 introduces **auto-discovery** (every action snippet becomes a chip automatically) and **signature-sourcing** (chip insertion text is derived from the snippet's `inputs:` frontmatter in canonical E-- form per B7.1), with `_chips.md` providing optional curation overrides. v3 extends both with subdirectory-aware palette context and chips-without-backing-files.

## Default behavior (no `_chips.md` present)

Auto-derivation rules apply to every snippet in active library subdirectories (per the v0.2.47 on-disk discovery):

### For action snippets

1. Skip if the snippet's frontmatter contains `chip: false`.
2. Skip if the snippet's basename starts with `_` (per constitution S7).
3. Otherwise:
   - **target**: the snippet_id.
   - **label**: humanized snippet_id (underscores → spaces, capitalized first letter). Example: `create_water_particles` → `Create water particles`.
   - **group**: parent subdirectory name relative to the library vault. Example: `forge-music/blues/song.md` → group `blues`. Snippets at the library root → group `(library)` or equivalent default label.
   - **insertion**: signature-derived per B7.1:
     - No inputs declared: `Do [[snippet_id]]().`
     - Inputs `[a, b]`: `Do [[snippet_id]](<a>, <b>).` Angle-bracketed placeholders prompt the user to fill in values; the cursor lands at the first placeholder after insertion.
     - For snippets that return values rather than discarding them (heuristic: name starts with `get_` / `compute_` / `make_` / etc., or otherwise unclear): `Set <result> to [[snippet_id]](<a>, <b>).` is acceptable as a refinement; default `Do` form is the safe choice.

### For data snippets

1. Skip if `chip: false` in frontmatter.
2. Skip if basename starts with `_`.
3. Otherwise:
   - **target**: the snippet_id.
   - **label**: humanized snippet_id.
   - **group**: same as action snippets (parent subdirectory).
   - **insertion**: `Set <name> to [[snippet_id]]().` Data snippets are invoked as no-arg calls in canonical E-- form; the engine's compute path returns the stored content when invoked. The leading `Set <name> to` is the standard receive-a-value shape; user replaces `<name>` with a binding name.

### For snapshot data snippets (system-generated, system-managed)

ALWAYS excluded from chips. Per S6 they're system-managed; per the Mission they're not user-authored building blocks.

## With `_chips.md` present

`_chips.md` is itself a data snippet (per current convention) but is excluded from auto-discovery via the `_` prefix per S7. Its content provides curation overrides.

### File shape

```yaml
---
type: data
content_type: yaml
read_only: true
description: <vault's chip curation notes>
schema_version: 2
---

# Body

```yaml
overrides:
  # Each entry overrides the auto-derived chip for one snippet.
  # Unspecified fields keep their auto-derived values.
  - target: create_water_particles
    label: "Spawn 500 water particles"
    group: "Setup"
    insertion: "Do [[create_water_particles]]()."
    order: 1

groups:
  # Optional: declare group order + display labels.
  # Ungrouped chips land in a default "Other" group at the end.
  - id: Setup
    order: 1
    label: "Setup chain"
  - id: Click
    order: 2
    label: "Click chain"

hide:
  # Optional shorthand: snippet_ids to omit from the palette.
  # Equivalent to `chip: false` in the snippet's frontmatter.
  - debug_internal_helper
```
```

### Override schema (per `overrides[]` entry)

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `target` | yes | snippet_id | — | Which snippet this override applies to. |
| `label` | no | string | humanized target | Display label in the palette. |
| `group` | no | string | parent subdir | Group ID; matches `groups[].id` if declared. |
| `insertion` | no | string | signature-derived | Custom insertion text. Must be B7.1-canonical when E-- migration completes. |
| `order` | no | int/float | alphabetical by label | Sort order within the group. |
| `hide` | no | bool | false | Alternative to listing in top-level `hide[]`. |

### Group schema (per `groups[]` entry)

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `id` | yes | string | — | Matches `overrides[].group` and auto-derived group values. |
| `order` | no | int/float | declaration order | Group order in the palette. |
| `label` | no | string | id | Group display label. |

### `hide[]` shorthand

Top-level `hide` is a list of snippet_ids to omit. Equivalent to per-snippet `chip: false` in frontmatter, but lets a vault curator hide a snippet without editing its source file. Use when the snippet author wants the chip visible by default and only a specific curator wants it hidden in their vault.

## Conflict resolution (frontmatter vs `_chips.md`)

**Frontmatter wins.** When a snippet's frontmatter has `chip: false` AND `_chips.md` has an explicit `overrides[]` entry for that snippet:
- The frontmatter opt-out is authoritative — the chip does NOT appear in the palette.
- Vault curators cannot override a snippet author's explicit opt-out.

This preserves authorial intent. If a curator believes a hidden chip should be surfaced, they coordinate with the snippet author rather than override silently.

The opposite case — snippet's frontmatter `chip: true` (default) but `_chips.md` lists target in `hide[]` — is uncomplicated: the chip is hidden in this vault's palette via curator decision. Other vaults that don't list it in `hide[]` see the chip.

## Merge logic

1. Compute auto-derived chip list per the rules above.
2. Apply `_chips.md` `overrides[]`: for each entry with matching `target` in the auto-derived list, replace specified fields; preserve unspecified fields.
3. Apply `_chips.md` `hide[]`: remove matching targets from the list.
4. Apply `_chips.md` `groups[]` to determine group display order + labels. Unreferenced groups keep their auto-derived names.
5. Sort within each group by `order` field (if specified), otherwise alphabetically by label.

## Error handling

- **Override target doesn't exist**: warning at palette-load time (logged to devtools console); the override is silently dropped. Possible causes: typo, snippet renamed, snippet deleted.
- **Malformed YAML in `_chips.md`**: warning + fall through to pure auto-discovery for that library. Palette still works; curation is just unapplied.
- **`schema_version` ≠ 2**: warning + skip the file. Forward-compatibility hook for future v3 changes.
- **Override targets a snippet with `chip: false` in frontmatter**: warning (override is ignored per the conflict-resolution rule above).

## Relation to constitution

- **S7**: `_*.md` files are infrastructure, excluded from auto-discovery (including `_chips.md` itself).
- **B7.1**: chips MUST produce canonical-E-- call syntax for their insertion text. Signature-sourced auto-derived insertions are B7.1-compliant by construction.

## Migration from v1

The current `_chips.md` files (e.g., `forge-moda/_meta/_chips.md`) are v1 shape:

```yaml
chips:
  - label: "Create water particles"
    insertion: "Call [[create_water_particles]]."  # NOT B7.1-canonical
    group: "Setup"
    refs: [create_water_particles]
```

v1 → v2 migration:
1. Each `chips[]` entry becomes an `overrides[]` entry: `label` field becomes a `target`-keyed override.
2. The `insertion` strings get rewritten to B7.1-canonical form (`Call [[X]].` → `Do [[X]]().`). This may be a manual rewrite or scripted, but the existing v1 entries CANNOT pass through to v2 unchanged — their insertion text is not canonical.
3. The `refs` field is dropped — refs are now derived from the canonical-form insertion via static analysis.
4. Add `schema_version: 2` to the file's frontmatter.
5. Migrate or add `groups[]` and `hide[]` blocks as the vault curator sees fit.

Vaults that don't migrate continue to work (v1 schema gracefully falls back to "no-curation, all-auto-discovered") but lose their existing curation. Curators are expected to migrate as a one-time touch when the chip-palette code adopts schema v2.

---

# v3 extensions (authorized 2026-06-06)

v3 adds two capabilities surfaced by forge-doc's Tier 1 tutorial proof-of-concept. The v2 surface stays intact; v3 layers on top. A v2 `_chips.md` works unchanged under v3 semantics.

## v3.1 — Per-chapter `_chips.md` walk-up discovery

**Problem v3.1 solves:** today there is ONE `_chips.md` per library vault, at `<vault>/_meta/_chips.md` or `<vault>/_chips.md`. The chip palette doesn't look inside subdirectories. For forge-doc's tutorial, this means every chapter's snippets surface in one palette simultaneously, breaking the "low floor, one concept at a time" pedagogy.

**v3.1 mechanism:** when computing the chip palette for an active file, the discoverer walks UP from the file's directory and accumulates `_chips.md` configuration at each level. Higher-specificity (closer to the file) wins.

**Walk order for an active file at `<vault>/<subdirA>/<subdirB>/snippet.md`:**

1. `<vault>/<subdirA>/<subdirB>/_chips.md` (most specific).
2. `<vault>/<subdirA>/_chips.md`.
3. `<vault>/_chips.md` or `<vault>/_meta/_chips.md` (least specific — current v2 location).

For each level, if `_chips.md` exists and parses as v2-shaped (or v3-shaped, see below), its configuration is merged into the accumulated palette config. Merging precedence:

- Lower-specificity `overrides[]` entries are SUPERSEDED by higher-specificity ones with the same `target`.
- Lower-specificity `hide[]` entries combine with higher-specificity ones (hide is union — once hidden, hidden).
- Lower-specificity `groups[]` entries are SUPERSEDED by higher-specificity ones with the same `id`.
- Lower-specificity `synthetic_chips[]` entries (per v3.2 below) combine with higher-specificity ones; same-`label` higher specificity wins.

**Auto-discovery scope changes with walk:** when a per-chapter `_chips.md` exists, the auto-discovery defaults narrow to snippets within that subdirectory. The current vault-wide auto-discovery is replaced (for that active file) by subdirectory-scoped auto-discovery. Example: with active file `forge-tutorial/01-hello/hello.md` and `forge-tutorial/01-hello/_chips.md` present, auto-discovery walks `forge-tutorial/01-hello/*.md` only, not the whole vault. Higher-level `_chips.md` (e.g., `forge-tutorial/_chips.md`) STILL contributes its `overrides`, `hide`, `groups`, and `synthetic_chips` — but auto-discovery's snippet enumeration is scoped to the active file's chapter.

**Forge-doc pedagogical pattern** (canonical example):

```
forge-tutorial/
├── _chips.md                          # global synthetic chips (print etc.); empty hide list
├── 01-hello/
│   ├── _chips.md                      # chapter-1 curation (only `print` visible)
│   └── hello.md
├── 02-variables/
│   ├── _chips.md                      # chapter-2: unhides Set
│   └── greeting.md
├── ...
└── 09-slots/
    ├── _chips.md                      # chapter-9: full vocabulary visible
    └── primes.md
```

Each chapter's `_chips.md` uses `hide[]` to suppress chips not yet introduced (referencing synthetic chip `label`s from the higher-level vault `_chips.md`).

## v3.2 — Synthetic chips (no backing snippet file)

**Problem v3.2 solves:** language constructs like `print`, `Set ... to ...`, `If ... Otherwise`, `For each ...`, `Define ... taking ...` are E-- builtins or syntax, not Forge snippets. Today's chips are auto-derived from `.md` snippet files. Language constructs have nothing on disk for chip discovery to find. This breaks forge-doc's tutorial sequence — chapter 1 should expose `print` as a chip; chapter 2 adds `Set` as a chip; etc.

**v3.2 mechanism:** a `synthetic_chips[]` section in `_chips.md` declares chips with explicit `insertion` text and no `target` (no backing snippet). Plugin renders them in the palette like regular chips. Clicking them inserts the declared text.

**Schema:**

```yaml
synthetic_chips:
  - label: "print"
    insertion: 'Do [[print]]("<message>").'
    group: "Builtins"
    order: 1
  - label: "Set"
    insertion: 'Set <var> to <value>.'
    group: "Statements"
    order: 1
  - label: "If"
    insertion: |
      If <condition>:
          <body>
    group: "Statements"
    order: 2
  - label: "For each"
    insertion: |
      For each <item> in <collection>:
          <body>
    group: "Statements"
    order: 3
  - label: "Define"
    insertion: |
      Define [[<name>]] taking <params>:
          <body>
    group: "Statements"
    order: 4
```

**Synthetic chip schema (per `synthetic_chips[]` entry):**

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `label` | yes | string | — | Display label in the palette (also the lookup key for `hide[]` and merging). |
| `insertion` | yes | string (single line or multi-line via `|`) | — | Text inserted into the editor at cursor position when chip is clicked. Should be B7.1-canonical where applicable. |
| `group` | no | string | "Synthetic" | Group ID; same semantics as v2's `overrides[].group`. |
| `order` | no | int/float | declaration order | Sort order within the group. |

**Hiding synthetic chips:** add the synthetic chip's `label` to `hide[]`. Same mechanism as hiding auto-derived chips.

**No `target` field on synthetic chips.** They don't refer to a snippet file. Distinguishes them from auto-derived chips at discovery time.

**Wikilink-click suppression note:** synthetic chip insertion text may contain `[[builtin_name]]` markup (e.g., `Do [[print]]("<message>").`). The v0.2.59+ B7.2 builtin-wikilink interception handles the click suppression so users don't create stray `print.md` files. This is the load-bearing dependency: synthetic chips work cleanly because B7.2 already suppresses the resulting wikilink clicks.

## v3 file-shape example

```yaml
---
type: data
content_type: yaml
read_only: true
schema_version: 3
description: forge-tutorial chapter 1 (Hello) — minimal vocabulary
---

# Body

```yaml
synthetic_chips:
  - label: "print"
    insertion: 'Do [[print]]("<message>").'
    group: "Builtins"

groups:
  - id: Builtins
    order: 1
    label: "Built-in functions"

hide:
  # Chapter 1 hides every synthetic chip from the vault-level _chips.md
  # except print (declared above as a chapter-local synthetic).
  - "Set"
  - "If"
  - "For each"
  - "Define"
  # ...etc, listed once at top-level _chips.md and hidden per chapter
```
```

## v2 → v3 migration

v2 `_chips.md` files work UNCHANGED under v3. No migration step required. Vaults that want to use v3.1 walk-up gain the capability by creating subdirectory `_chips.md` files; vaults that want v3.2 synthetic chips bump `schema_version: 2 → schema_version: 3` in their existing `_chips.md` and add a `synthetic_chips[]` section.

Backward-compat is guaranteed for v2 → v3: a v3-aware plugin reads a v2 file as a single-level walk (no subdirectory enumeration) with no synthetic chips, which is exactly the v2 behavior.

## Error handling

In addition to v2's error handling rules:

- **`schema_version` < 2** (treated as v1 today): unchanged; falls through to auto-discovery.
- **`schema_version` ≠ 2 and ≠ 3**: warning + skip the file. Forward-compatibility hook for future v4+ changes.
- **`synthetic_chips[]` entry missing required `label` or `insertion`**: warning, that entry dropped, rest of file processed.
- **Subdirectory `_chips.md` parse error during walk**: warning, that level skipped, walk continues with the other levels.

## Relation to constitution

- **B7.1**: synthetic chip insertion text MUST be B7.1-canonical for snippet calls. For pure language constructs (`Set <var> to <value>.`), canonical form applies but `[[ ]]` markers are not used (these are statements, not calls).
- **B7.2**: synthetic chips for Python builtins like `print` rely on B7.2 wikilink-click suppression for clean UX (no stray `print.md` files).
- **S7**: `_chips.md` (and any other `_*.md`) remain infrastructure files, excluded from auto-discovery as snippets — including in subdirectory walks per v3.1.
