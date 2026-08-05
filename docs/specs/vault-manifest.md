# Vault Manifest Specification

## Status
Draft v1 — 2026-04-28

## Purpose
Every vault — authoring or library — has a manifest at its root that
declares its identity and dependencies. The manifest is the contract
between Forge's resolver, the install machinery, and the user's intent.

## File
- Filename: `forge.toml`
- Location: at the root of the vault (next to snippet markdown files)
- Format: TOML 1.0
- Encoding: UTF-8

## Required fields

### `name` — string
The canonical name of the vault.
- 3–64 characters
- Lowercase ASCII letters, digits, and hyphens
- Must start with a letter
- For library vaults, must equal the registry entry name and the
  containing folder name in the user's Obsidian vault. This three-way
  alignment is what makes Obsidian's path-based wikilinks resolve to
  Forge's namespaces.

### `version` — string
SemVer 2.0.0 string (e.g., "0.1.0"). For authoring vaults that are
not published, any valid SemVer is acceptable; "0.0.0" is conventional.

### `description` — string
One-sentence human-readable description. 1–200 characters.

## Optional fields

### `dependencies` — array of tables
List of declared library vaults this vault depends on. Each entry has:
- `name` — string; canonical name of the dependent vault
- `version` — string; exact SemVer (no ranges in v1)

Default: empty (no dependencies).

The order of entries matters: it determines resolution order for bare
references (per ADR 0002).

## Example: authoring vault

    name = "my-vault"
    version = "0.0.0"
    description = "John's working vault."

    [[dependencies]]
    name = "forge-core"
    version = "0.1.0"

## Example: library vault

    name = "forge-core"
    version = "0.1.0"
    description = "Forge bootstrap demo vault."

## Optional section: `[imports]`

A vault may declare other vaults whose notes its Recipes can reference.
The schema, resolution order, and collision policy are specified
separately in [vault-imports.md](vault-imports.md) — it is large enough
to warrant its own document, and forge-mcp, forge-transpile and
forge-client-obsidian all target it.

Spec only as of drain `2026-08-03-1500`; nothing reads `[imports]` yet.

One constraint belongs here rather than there, because it is a property
of this file's shape: every other field in `forge.toml` is a top-level
key, and in TOML every key following a `[table]` header belongs to that
table. **`[imports]` must be the last section in the file.** Above the
flat keys it silently reparents them, producing a manifest with no
`name` instead of an error.

## Validation
Forge validates manifests at:
- Vault load — any failure aborts loading that vault and surfaces a
  structured error
- Install completion — the downloaded vault's manifest is checked
  against the registry entry; mismatch is a hard error per ADR 0003

Validation rules:
- All required fields present
- `name` matches the format above
- `version` is valid SemVer
- For library vaults, declared `name` and `version` match what the
  registry promised

## Compatibility and evolution
This spec is v1. Adding new optional fields to the manifest is
backward-compatible. Removing or changing semantics of existing
fields requires a new spec version, signaled by a `schema_version`
field added to the manifest. v1 manifests are recognized by the
absence of `schema_version`.