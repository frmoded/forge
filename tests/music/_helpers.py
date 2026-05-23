"""Non-fixture helpers for the forge-music sanity tests.

Mirrors `tests/moda/_helpers.py`'s shape: conftest.py is fixture-only;
plain functions live here so test modules can import by name.

`_find_vault()` locates the forge-music vault. Today the published
vault at `~/projects/forge-music/` is the source of truth (no
authoring-vault layer like forge-moda has). When/if a forge-music
authoring vault appears, add it to `_CANDIDATES`.
"""
import os
from pathlib import Path


_CANDIDATES = [
    os.environ.get("FORGE_MUSIC_VAULT_PATH"),
    os.path.expanduser("~/projects/forge-music"),
]


def _find_vault():
    for c in _CANDIDATES:
        # Pick the first candidate that has the blues form snippet on
        # disk — narrow enough to avoid grabbing an empty repo, broad
        # enough to work whether the vault grows to N snippets.
        if c and Path(c, "form.md").is_file():
            return c
    return None
