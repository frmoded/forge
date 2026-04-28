# ADR 0003: Vault distribution via per-vault GitHub repositories

## Status
Accepted — 2026-04-28

## Context
Vaults need to be downloadable, version-pinned, and integrity-checkable.
They are content-light (a manifest plus a handful of markdown files)
but must be reliably retrievable. We want to avoid running our own
hosting infrastructure for v1 while keeping the door open to migrating
later.

## Decision
Each published vault lives in its own dedicated GitHub repository.

- Repository naming: vault name maps directly to repo name (e.g., the
  vault `forge-core` lives at `<owner>/forge-core`).
- Versions are released as annotated git tags following Semantic
  Versioning, prefixed with `v` (e.g., `v0.1.0`).
- The vault's contents at a given tag are the contents of the vault:
  a `forge.toml` manifest at the repo root, plus snippet markdown
  files (organized in subdirectories as the vault sees fit).
- Tarballs are served via GitHub's archive endpoint:
  `https://github.com/<owner>/<repo>/archive/refs/tags/v<X>.<Y>.<Z>.tar.gz`.
  No GitHub Releases required — the archive endpoint serves any tag.
- Tarballs are verified via SHA-256 hashes recorded in the registry
  index alongside each version's tarball URL.
- When extracting, the top-level wrapper directory that GitHub adds
  (`<repo-name>-<version>/`) is stripped to expose `forge.toml` at
  the extraction root.

## Consequences
- Zero hosting cost. GitHub serves everything.
- Per-vault git history doubles as per-vault release history. Diffs
  between versions are reviewable directly on GitHub.
- Anyone with a GitHub account can publish a vault — they create a
  repo, tag a version, and submit a PR to the registry index.
- Per-vault repos keep concerns separated. A vault's CI, issues, and
  documentation live with the vault.
- GitHub guarantees stability of archive tarballs for git tags as of
  current policy. If this changes, the registry's recorded SHAs would
  reject tampered downloads, surfacing the issue immediately rather
  than silently corrupting installs.
- Migrating to a different hosting model later (e.g., a real registry
  with hosted tarballs) requires only changing the URLs in the
  registry index. Install-side code is unaffected.
- For v1, the only published vault is `forge-core` at
  `frmoded/forge-core`.