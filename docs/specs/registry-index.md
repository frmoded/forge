# Registry Index Specification

## Status
Draft v1 — 2026-04-28

## Purpose
The registry index is the canonical catalog of published vaults. It
maps vault names to download locations and integrity hashes. It is
the source of truth that the install snippet consults.

## File
- Filename: `index.json`
- Location: at the root of the registry repository (e.g.,
  `frmoded/forge-registry/index.json`)
- Format: JSON
- Encoding: UTF-8, no BOM
- Style: 2-space indent for human review

## Top-level fields

### `schema_version` — string
Version identifier for this schema. v1 indices use `"1"`. Future
incompatible schema changes bump this number.

### `vaults` — object
Map from vault name to vault metadata. Keys must match the canonical
vault name format defined in the Vault Manifest spec.

## Per-vault fields

### `description` — string
One-sentence description. Denormalized from the vault's own manifest
into the index for browsability.

### `homepage` — string (optional)
URL to the vault's home, typically its GitHub repository.

### `latest` — string
Version string (matching a key in `versions`) that should be used when
no version is specified at install time.

### `versions` — object
Map from SemVer version string to per-version metadata. At least one
version is required.

## Per-version fields

### `tarball` — string
Fully-qualified HTTPS URL pointing to a gzipped tarball of the vault
contents at this version. For GitHub-hosted vaults, this follows the
pattern in ADR 0003:
`https://github.com/<owner>/<repo>/archive/refs/tags/v<X>.<Y>.<Z>.tar.gz`.

### `sha256` — string
Lowercase hex-encoded SHA-256 hash of the tarball contents. Length 64.
The install snippet verifies the downloaded tarball against this hash;
mismatch is a hard error.

## Example

    {
      "schema_version": "1",
      "vaults": {
        "forge-core": {
          "description": "Forge bootstrap demo vault.",
          "homepage": "https://github.com/frmoded/forge-core",
          "latest": "0.1.0",
          "versions": {
            "0.1.0": {
              "tarball": "https://github.com/frmoded/forge-core/archive/refs/tags/v0.1.0.tar.gz",
              "sha256": "<lowercase-hex-sha256>"
            }
          }
        }
      }
    }

## Validation
Forge validates the index after fetch:
- `schema_version` equals a known value (currently `"1"`)
- `latest` points to an existing key in `versions`
- All `tarball` values are HTTPS URLs
- All `sha256` values are 64-character lowercase hex
- All version keys are valid SemVer

Failed validation aborts the install with a structured error.

## Compatibility and evolution
Adding new optional fields (per-vault or per-version) is
backward-compatible — older Forge clients ignore unknown fields.
Removing or repurposing fields requires a new `schema_version`. If a
breaking change is ever needed, the previous `index-v1.json` should
remain accessible at a versioned URL so older Forge clients continue
to work.