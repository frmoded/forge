"""E-- vendored into Forge — deterministic English-canonical compiler.

Source-of-truth lives at `~/projects/e--/src/`. This package is a
sync'd mirror — do NOT edit files here directly. Use
`~/projects/forge/scripts/sync-emm.mjs` to re-pull when E--'s upstream
moves; surface upstream-bound bug reports via
`~/projects/forge-moda-bootstrap/e-minus-minus-feedback.md`.

Pinned version is recorded in `VERSION`. Upstream-bare-name imports
(`from lexer import tokenize`) are converted to package-relative
(`from .lexer import tokenize`) here for Python package conventions —
the only deviation from byte-equal mirroring. Sync script applies the
same transformation automatically.

Stage 2 (v0.2.55, opt-in via `facet_form: canonical`) wires the
public `transpile` entry point into `forge.core.executor` so canonical
snippets compile to Python at runtime without an LLM call. Free-English
snippets continue through the `/generate` LLM path.
"""

from .transpiler import transpile
from .errors import (
    EmmSyntaxError,
    EmmResolveError,
    EmmNormalizeError,
)

__all__ = [
    "transpile",
    "EmmSyntaxError",
    "EmmResolveError",
    "EmmNormalizeError",
]
