# Built-in Vault Contract

## Status
Draft v1 — 2026-04-28

## Purpose
The built-in vault is a synthetic vault registered by the Forge backend
at startup. It contains the install machinery and other platform-level
snippets that must be available before any user or library vault is
loaded (per ADR 0001). This document describes the contract between
the built-in vault implementation and the rest of the system.

## Identity
- Namespace: `forge` (fixed; not configurable)
- Source: bundled inside the `forge` Python package
- On-disk location inside the package: `forge/builtins/snippets/`

The built-in vault has no manifest file, no on-disk presence in the
user's Obsidian vault, and no entry in the registry index.

## Loading
At backend startup, the snippet registry:
1. Recursively reads every `.md` file under `forge/builtins/snippets/`.
2. Parses each as a hybrid snippet (frontmatter + facets), using the
   same parser as filesystem-scanned vaults.
3. Constructs in-memory snippet objects, tagged with `vault = "forge"`
   and `source = "builtin"`.
4. Registers them in the snippet index under the `forge` namespace.

Built-in snippets share the same internal data structure as filesystem
snippets; the only difference is the `source` field and the absence
of a filesystem path within the user's vault.

## Snippet IDs and subdirectory layout
Subdirectories under `forge/builtins/snippets/` become part of the
snippet ID within the namespace, mirroring how Obsidian's path-based
wikilinks behave. Examples:

- `forge/builtins/snippets/install.md` → `forge/install`
- `forge/builtins/snippets/registry/lookup.md` → `forge/registry/lookup`
- `forge/builtins/snippets/vault/extract.md` → `forge/vault/extract`

This structure is purely organizational — there is no notion of
"sub-vaults" — but it allows logical grouping of related sub-snippets.

## Resolution
- Built-ins resolve last per ADR 0002.
- Bare references match built-ins only if no authoring or library
  vault provides the name.
- Qualified references (`forge/install`) always resolve to the
  built-in regardless of authoring-side overrides.

## Override behavior
A user can shadow a built-in by creating a snippet of the same name in
their authoring vault. This is intentional — useful for testing
modified install logic or patching behavior locally without forking
Forge. The original built-in remains accessible via its qualified
reference.

## Read-only guarantees
- Built-in snippets are read-only at runtime; the system never writes
  to `forge/builtins/snippets/`.
- They are updated only by upgrading the `forge` package.
- They never appear in the user's Obsidian vault filesystem, graph
  view, backlinks, or search.

## Initial inventory (v1)
The v1 built-in vault contains:

- `forge/install` — top-level orchestrator for vault installation
- `forge/registry/lookup` — fetch and parse the registry index, find
  a vault entry
- `forge/registry/fetch` — download and SHA-verify a tarball
- `forge/registry/refresh` — trigger a backend rescan after install
- `forge/vault/extract` — extract a verified tarball into the user's
  Obsidian vault
- `forge/manifest/add_dep` — add or update a dependency entry in the
  authoring vault's manifest

Future commands (`update`, `uninstall`, `list`) will be added in later
milestones.

## Testing
Built-in snippets are tested as part of the `forge` package's test
suite. Each snippet has unit tests that mock external dependencies
(HTTP, filesystem); the integration test of the full install flow
exercises all built-ins together.

## Adding new built-ins
Adding a built-in is a code change to the `forge` package:
1. Add the markdown file under `forge/builtins/snippets/`.
2. Add tests.
3. Bump the `forge` package version per its own SemVer policy.

## Future migration to library vaults
A future Forge release may move some user-facing convenience commands
out of built-ins and into a library vault distributed through the
registry. This is acceptable as long as the install machinery itself
remains built-in — the chicken-and-egg constraint applies only to
install. Such a migration is a backward-incompatible change to user
workflows and would be announced ahead of time.