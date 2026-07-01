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
    # Probe a stable canonical note that has survived every rename +
    # promotion so far:
    # - v0.3.3: form.md moved into blues/.
    # - v0.7.0: form.md promoted to forge.music.lib.form (deleted).
    # - v0.8.0: blues/ → slow_burn/.
    # The 12-bar blues progression data note has moved along with the
    # directory renames but has never been promoted to a lib function
    # (data notes stay in the vault by design).
    #
    # Drain 2026-07-02-1930 migrated test_blues_form + test_loom to
    # call forge.music.lib functions directly, so those tests no
    # longer need this helper. It stays for any future test that
    # legitimately needs vault-level integration (registry resolution,
    # snapshot capture, edge cases).
    for c in _CANDIDATES:
        if c and Path(c, "slow_burn", "twelve_bar_blues_progression.md").is_file():
            return c
    return None
