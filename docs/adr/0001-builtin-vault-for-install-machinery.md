# ADR 0001: Built-in vault for install machinery

## Status
Accepted — 2026-04-28

## Context
Forge lets users install vaults from a registry via an `install` snippet.
The install snippet itself cannot live in the registry — nothing would
exist to fetch it on a fresh install. It also should not live in the
user's Obsidian vault as editable files, because it is infrastructure,
not user content. We need a way to make install (and its companion
commands) available to every Forge user, on day one, without on-disk
presence in their vault.

## Decision
The install machinery and related platform commands ship bundled inside
the `forge` Python package as a "built-in vault."

- On-disk location inside the package: `forge/builtins/snippets/`
- Each built-in snippet is a markdown file using the standard hybrid
  format (frontmatter + English facet + Python facet).
- On backend boot, the snippet registry scans this directory and
  registers its contents as a synthetic vault under the namespace
  `forge`.
- Built-in snippets do not appear in the user's Obsidian vault filesystem.
- Built-in snippets are read-only from the user's perspective; updating
  them happens by upgrading the `forge` package.
- Initial built-ins for v1: `install`, and the sub-snippets
  `registry/lookup`, `registry/fetch`, `vault/extract`,
  `manifest/add_dep`, `registry/refresh`. `update`, `uninstall`, and
  `list` are deferred to a later milestone.

## Consequences
- Users can invoke `[[install]] "forge-core"` from any note without
  having installed anything first.
- Bare references like `[[install]]` resolve via the resolution order
  defined in ADR 0002; qualified references like `[[forge/install]]`
  always work.
- Users can override a built-in by defining a snippet of the same name
  in their authoring vault — useful for testing modified install logic
  without forking Forge.
- Built-in snippets ship as part of every Forge release and are tested
  as part of the Forge test suite.
- The package layout commits to a `forge/builtins/` directory; this is
  a public-facing convention even though end users never see it.