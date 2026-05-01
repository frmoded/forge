# Install flow — plugin reference

This is what the Obsidian plugin needs to know to drive `[[install]]` over the
HTTP API. Audience: someone wiring the plugin's "install" UX. The runtime
already implements everything described here; nothing here is aspirational.

## Trigger

Plugin POSTs `/compute`:

```json
{
  "vault_path": "/path/to/authoring/vault",
  "snippet_id": "install",
  "inputs": {"vault_name": "forge-core"}
}
```

Optional `inputs.version` pins to a specific SemVer. Omitted means "latest"
(resolved from the registry index's `latest` field).

The plugin must have called `/connect` for `vault_path` first. `install` is a
built-in snippet (resolves via ADR 0002 last-source fallback) so a bare
`snippet_id: "install"` works as long as the user hasn't shadowed it in their
authoring vault.

## Success response

`200 OK`:

```json
{
  "type": "action",
  "stdout": "...",
  "result": {
    "vault_name": "forge-core",
    "version": "0.1.0",
    "message": "Installed forge-core@0.1.0. Now try [[forge-core/...]] to invoke any of its snippets."
  }
}
```

The `result.message` is human-readable and includes the post-install hint.
Render it verbatim in the output panel.

## Post-install refresh

After a successful install, the plugin should `POST /connect` again with the
same `vault_path`. The response includes a `snippets` map:

```json
{
  "status": "connected",
  "vault_path": "...",
  "warnings": [],
  "snippets": {
    "authoring": ["my_note", ...],
    "forge-core": ["hello_registry", ...],
    "forge": ["install", "registry/lookup", "registry/fetch", ...]
  }
}
```

Keys are vault namespaces; values are bare snippet IDs within each namespace.
Use this to populate autocomplete and to confirm the new vault is live.

The backend keeps the registry instance live across `/compute` calls — the
install's internal `forge/registry/refresh` step mutates it in place — so the
second `/connect` reflects post-install state without a force flag. (POST
`/connect` with `force: true` would re-scan the filesystem; not required here.)

## Failure response

`422 Unprocessable Entity` with the same shape used by other failed snippet
executions:

```json
{
  "detail": {
    "error": "<one-line cause>",
    "stdout": "<anything the snippet printed before failing>"
  }
}
```

Common error causes the plugin should expect:

| Cause                                | `error` excerpt                                       | UX guidance                                    |
| ------------------------------------ | ----------------------------------------------------- | ---------------------------------------------- |
| Registry unreachable                 | `connection failed` / `timed out`                     | "Couldn't reach the registry — check network." |
| Vault not in registry                | `vault '<name>' not in registry`                      | "Unknown vault. Check spelling."               |
| Pinned version not in registry       | `vault '<name>' version '<v>' not in registry`        | "That version doesn't exist. List versions."   |
| Tarball SHA mismatch                 | `hash mismatch: actual=... expected=...`              | "Download corrupted. Try again."               |
| Path-traversal in tarball            | `'..' segment in tarball entry: ...`                  | "Vault tarball is malformed. Report to author."|
| Manifest missing/invalid in vault    | `manifest not found at .../forge.toml`                | "Vault is malformed. Report to author."        |
| Schema validation failure (registry) | `unsupported schema_version` / `must be HTTPS URL`    | "Registry is incompatible. Update Forge."      |

`stdout` may carry the snippet's own progress prints (currently none) — render
it underneath the error if non-empty.

## Cancellation

Out of scope for v1. Install is fire-and-forget at the HTTP layer. If a user
aborts the plugin mid-install, the backend completes the install in the
background. A subsequent `/connect` will show the vault installed. Plugin
should not assume "the user clicked away" means "the install rolled back" —
it didn't.

## Concurrency

- Two installs of the **same** vault running concurrently are safe. The tarball
  cache keys by SHA-256, so both downloads write to the same file; whichever
  finishes second overwrites with identical bytes. Both succeed.
- Two installs of **different** vaults running concurrently are safe. Each
  goes through its own pipeline; they share the registry index cache (5-min
  TTL) but don't otherwise contend.
- Concurrent install + compute of an unrelated snippet is safe. `/compute`
  doesn't lock the registry; the in-place mutation by `forge/registry/refresh`
  is a single dict reassignment.

The plugin doesn't need to serialize installs unless it wants to.
