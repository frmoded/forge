# Vault imports

## Status

**Spec only.** Phase 1 of the music-theory/music-core vault split (drain
`2026-08-03-1500`). Nothing implements this yet — forge-mcp,
forge-transpile and forge-client-obsidian all target it in phases 2–4.
The point of writing it first is that three codebases have to agree on
resolution order and collision policy, and agreeing after the fact means
reconciling three different guesses.

## Purpose

Let one vault reference notes that live in another, reproducibly.

Today a wikilink `[[chord_progression]]` resolves within a single vault
plus the engine library. That forces a choice between duplicating shared
primitives into every vault that needs them, or piling unrelated material
into one vault so everything can see it. Imports are the third option:
a vault declares which other vaults it draws on, pinned to an exact
commit.

`forge.toml` is specified in [vault-manifest.md](vault-manifest.md);
this document specifies the `[imports]` section it may contain.

## Schema

`[imports]` is an optional top-level section. One entry per imported
vault, keyed by the import's name:

```toml
[imports]
music-core = { git = "https://github.com/frmoded/music-core.git", sha = "abc12345", tag = "v0.3.0" }
```

| Field | Required | Meaning |
|---|---|---|
| `git` | yes | Git URL of the imported vault. |
| `sha` | yes | 8–40 char git SHA. The exact pin; this is what makes a build reproducible. |
| `tag` | no | Human-readable hint, e.g. `v0.3.0`. **Not authoritative** — on any disagreement the SHA wins. |
| `local` | no | Path to a local checkout. Developer override; wins over `git`+`sha` when present. |

### `local` alone is valid (amended by Phase 2, drain 2026-08-05-0710)

As first written, `git` and `sha` were required and `local` was a
developer override layered on top. Implementing Phase 2 showed that does
not work for the phase it was written for: there is no remote for
music-core yet, so a local-only import would have to name a git URL that
does not exist and a SHA that means nothing, purely to satisfy a
validator.

So: **`local` alone is a complete declaration.** `git` and `sha` remain
required when `local` is absent. The reproducibility argument for
pinning is untouched — it simply does not apply to an import you are
pointing at a directory on your own disk.

```toml
[imports]
music-core = { local = "../music-core" }              # valid
music-core = { git = "...", sha = "abc12345" }        # valid
music-core = { git = "...", sha = "...", local = "../music-core" }  # valid; local wins
```

Relative `local` paths resolve against the **importing vault's**
directory, not the process working directory, so a manifest means the
same thing wherever the server runs from.

### Placement matters

`forge.toml` is currently a flat file — `name`, `version`,
`description`, `domains` at top level, no tables. In TOML, every key
after a `[table]` header belongs to that table. **`[imports]` must
therefore be the last section in the file.** Putting it above the
existing flat keys silently reparents them into `imports`, and the
result is a vault with no `name` rather than a clear error.

Tooling that writes `forge.toml` programmatically must append, never
prepend.

### `local` is a developer override, not shared config

`local` points at one machine's filesystem. A `forge.toml` committed
with a `local` entry breaks for everybody else, and worse, breaks
*quietly* — they get whatever their own path resolves to, or a
not-found. Validation should warn when `local` is present in a
committed manifest.

## Validation

Checked at catalog-load time in forge-mcp:

1. **Name agreement** — the import key must equal the imported vault's
   own `name` in its `forge.toml`. Mismatch is an error, not a warning:
   it means the manifest and the thing it points at disagree about what
   the thing is.
2. **No cycles** — A importing B importing A is rejected. Report the
   full cycle, not just the edge that closed it.
3. **SHA drift** — declared `sha` differs from the fetched HEAD: warn,
   then **use the declared SHA**. Reproducibility beats freshness; a
   silent upgrade to whatever happens to be on the branch today is the
   failure mode pinning exists to prevent. The warning's job is to tell
   a developer they probably forgot to push or forgot to bump.

## Resolution order

For a wikilink in a Recipe body, resolve in this order and stop at the
first match:

1. **Local vault** — `<vault-root>/**/<note-id>.md`
2. **Declared imports**, in the order they appear in `[imports]` —
   `<import-root>/**/<note-id>.md`
3. **Engine library** — a function named `<note-id>` in `forge.<domain>.lib`
   for an active domain
4. **No match** — compile error naming every location searched, and
   suggesting `[[import-name:note-id]]` in case the note lives in an
   import that wasn't declared.

Local-first is deliberate: a vault's own notes are the ones its author
controls, and an import silently shadowing a local note would make a
vault's behaviour depend on somebody else's repo.

Import order being significant is a consequence of stop-at-first-match.
It also means reordering `[imports]` can change which note resolves —
worth saying out loud, because a TOML reformatter that sorts keys would
be a behaviour change.

## Collisions

Two locations resolving the same bare `note-id` is an error, not a
silent pick. The compile error names both:

```
error: wikilink [[chord_progression]] resolves ambiguously:
  - local vault (~/projects/music-theory/exercises/chord_progression.md)
  - imported vault music-core (~/projects/music-core/composition/chord_progression.md)
disambiguate with [[local:chord_progression]] or [[music-core:chord_progression]].
```

This is a deliberate exception to "stop at the first match". Order
decides which vault answers when the author *didn't know* there was a
choice; that's a convenience for the common case, not a rule worth
resolving a genuine ambiguity by. Erroring costs the author one
disambiguation; guessing costs them a note that quietly does something
else.

### Namespace syntax

`[[import-name:note-id]]` names the source explicitly. `[[local:...]]`
is reserved for the containing vault. Both forms are always accepted,
not only after a collision — an author who knows where a note comes from
can say so, and that reference stays correct if a collision appears
later.

An import named `local` is rejected at validation time; it would make
`[[local:x]]` ambiguous, which is the one thing this syntax exists to
prevent.

## Open questions for phase 2

- **Where does the fetched import live on disk?** A shared cache
  (`~/.forge/imports/<name>/<sha>/`) dedupes across vaults and makes the
  SHA visible in the path. Per-vault checkouts are simpler but duplicate.
  Not decided here.
- **When does the fetch happen?** Catalog load is the natural point, but
  it makes a network call part of opening a vault. An explicit
  `forge_sync_imports` keeps load offline at the cost of a step to forget.
- **Does the Obsidian plugin show imported notes in the palette?** They
  are resolvable, so arguably yes; but they aren't editable in place,
  and a palette that mixes the two invites edits that get discarded.
