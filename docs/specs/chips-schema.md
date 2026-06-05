# `_chips.md` schema v2 — auto-discovery + signature-sourcing + curation overrides

**Status:** committed 2026-06-04. Awaiting CC drain to adopt in the chip-palette code path.

This document specifies the v2 schema for the chip palette in Forge plugins. v1 was the vault-explicit-only shape (every chip hand-authored in `_chips.md`). v2 introduces **auto-discovery** (every action snippet becomes a chip automatically) and **signature-sourcing** (chip insertion text is derived from the snippet's `inputs:` frontmatter in canonical E-- form per B7.1), with `_chips.md` providing optional curation overrides.

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
