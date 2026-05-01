# Forge Smoke Test

A manual checklist to validate the full Forge stack end-to-end. Run
this after every release of the `forge` package or
`forge-client-obsidian` plugin, and any time the registry index or
`forge-core` vault is updated.

The smoke test exercises every architectural layer: backend startup,
plugin connection, registry fetch, install pipeline, cross-vault
snippet resolution, and execution. Total time: ~5 minutes.

## Prerequisites

- A working `forge` checkout with the venv set up.
- A working `forge-client-obsidian` checkout, built (`npm run build`).
- An Obsidian vault dedicated to smoke testing (or willingness to
  reset one).

## Reset to a clean state

In your smoke-test Obsidian vault, delete the following if present:

- `Welcome.md` (vault root)
- `.forge/initialized` (vault root, hidden)
- `forge-core/` (vault root)
- `forge.toml` (vault root, if it was auto-created by a previous run)

Stop any running Forge backend.

## Steps

### 1. Start the backend