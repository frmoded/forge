# Tech debt

## Per-vault Python dependencies

Today, third-party Python libraries that vaults need are installed globally
in the Forge backend's environment. The `forge-music` vault depends on
`music21`, so `music21` is currently listed alongside FastAPI and the rest
of Forge's runtime deps in `pyproject.toml`.

This means every Forge install pays the cost of `music21` even if the user
never installs `forge-music`. The cost today is small — `music21` is pure
Python, no native compilation — but the principle is wrong. A backend
shouldn't pre-install every library every published vault might ever need.

The principled solution is **per-vault Python dependency isolation**: each
vault's `forge.toml` declares its Python deps; install provisions a
per-vault virtualenv (or PEP 723-style inline metadata, or another
isolation primitive); the snippet runtime routes a vault's snippets to its
dedicated environment.

### Why we're not doing it now

- **Music is the only confirmed near-term consumer** of third-party Python
  libs. One data point isn't enough to design the boundary against.
- **`music21` is small and pure-Python** — no native deps, no compile
  step, ~30 MB on disk. Adding it globally has minimal footprint cost.
- **Designing the isolation primitive prematurely is expensive**: the
  install-time provisioning logic, the runtime dispatch, and the
  user-facing UX (deps in `forge.toml`, lockfiles?, upgrade flow?) all
  need decisions, and we don't yet have lived experience to know which
  choices matter.
- **The pain we'd be solving for hasn't surfaced.** No vault's deps
  conflict with another's; the global install hasn't gotten heavy enough
  to bother users.

### When to revisit

- A second vault wants a third-party Python lib whose version range
  conflicts with an existing one.
- The backend install footprint exceeds a threshold that bothers users
  (rough order of magnitude: ~200 MB).
- A proposed vault needs a library with native deps (`numpy`, `scipy`,
  `pandas`-with-extras) that meaningfully increases install size or
  install-time risk for users who don't need that vault.

Until one of those, deps stay in `pyproject.toml`. New per-vault deps
need review before merging — the bar is "would this be acceptable as a
permanent backend dep?", not "this vault needs it."
