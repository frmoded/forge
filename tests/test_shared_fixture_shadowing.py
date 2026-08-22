"""Drain 2026-08-22-1900 — no test file may re-use a name the shared
test layer already defines.

The founding incident (drain 1210 §5.3): `tests/moda/test_go_snapshot.py`
carried a private `_run` beside `conftest.py`'s shared one. The shared
copy was migrated to V2 at v0.2.196; the private copy was missed. The
drift produced three false failures and cost a root-cause cycle — and
worse, let a real content bug hide behind a test artifact.

Deliberate divergence is fine and often necessary (a fixture that needs
an isolated vault copy, a helper that drives a raw callable). What is
NOT fine is a divergent copy wearing the SAME NAME as the shared one:
that is what makes two different behaviours look like one thing at a
glance.

So the rule this guard enforces is about names, not about duplication:
**a test module may not define a function whose name also appears in
the shared layer visible to it** (its package's `conftest.py` at any
ancestor level within tests/, or a sibling `_helpers.py`) — at any
nesting depth, because the founding incident's collision was between
two *inner* closures.

Mechanism-based by construction: it walks definitions with `ast` rather
than grepping for names anyone guessed in advance, so a helper renamed
or added tomorrow is covered without editing this file.
"""
import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent


def _defs_at_any_depth(source: str) -> set:
    """Every function name defined anywhere in `source`, including
    closures nested inside fixtures — the founding collision was two
    inner `_run`s, which a top-level-only walk would miss."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _shared_names_visible_to(test_file: Path) -> dict:
    """{name: source-file} for the shared layer this test file can see:
    conftest.py in every ancestor dir up to tests/, plus a sibling
    _helpers.py."""
    names = {}
    directory = test_file.parent
    while True:
        for candidate in ("conftest.py", "_helpers.py"):
            path = directory / candidate
            if path.exists():
                for name in _defs_at_any_depth(path.read_text()):
                    names.setdefault(name, path.relative_to(TESTS_ROOT))
        if directory == TESTS_ROOT:
            break
        directory = directory.parent
    return names


def _shadowing_hits(test_files):
    hits = []
    for test_file in sorted(test_files):
        shared = _shared_names_visible_to(test_file)
        for name in sorted(_defs_at_any_depth(test_file.read_text())):
            if name.startswith("test_"):
                continue
            if name in shared:
                hits.append(
                    f"{test_file.relative_to(TESTS_ROOT)} defines {name!r}, "
                    f"which {shared[name]} also defines"
                )
    return hits


def test_no_test_file_shadows_a_shared_helper_name():
    test_files = [
        p for p in TESTS_ROOT.rglob("test_*.py")
        if "__pycache__" not in str(p) and p.name != Path(__file__).name
    ]
    assert len(test_files) > 50, "sweep found implausibly few test files"
    hits = _shadowing_hits(test_files)
    assert hits == [], (
        "private copies of shared test helpers drift (drain 1210's `_run`). "
        "Migrate to the shared version, or rename the local one and say why:\n  "
        + "\n  ".join(hits)
    )


def test_non_vacuity_the_detector_actually_detects(tmp_path):
    """Prove the sweep can fail. Without this, a bug in the AST walk
    (or an empty file list) would make the guard above pass silently —
    the exact vacuous-green shape drain 2300 §L32 guards elsewhere."""
    pkg = tmp_path / "tests"
    pkg.mkdir()
    (pkg / "conftest.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef runner():\n"
        "    def _run(x):\n        return x\n    return _run\n"
    )
    shadowing = pkg / "test_shadow.py"
    shadowing.write_text("def _run(x):\n    return x * 2\n\ndef test_a():\n    pass\n")
    clean = pkg / "test_clean.py"
    clean.write_text("def _run_isolated(x):\n    return x\n\ndef test_b():\n    pass\n")

    global TESTS_ROOT
    original = TESTS_ROOT
    try:
        TESTS_ROOT = pkg
        assert _shadowing_hits([shadowing]), "detector missed a real shadow"
        assert _shadowing_hits([clean]) == [], "detector flagged a distinct name"
    finally:
        TESTS_ROOT = original
