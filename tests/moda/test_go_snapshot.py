"""go's C8 snapshot-default behavior (read-snapshot-and-step).

These run against an ISOLATED copy of the moda vault (no `.forge/`)
so the snapshot-accumulation behavior is deterministic and doesn't
pollute the authoring vault. exec_python with vault_path set captures
outbound edges exactly like the server, so a first go() call writes
go's outbound snapshots that the second call then reads back.
"""
import shutil

import numpy as np
import pytest

from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import extract_python, exec_python
from tests.moda._helpers import make_state, _find_vault


@pytest.fixture
def vault_copy(tmp_path):
    src = _find_vault()
    if src is None:
        pytest.skip("no moda vault found")
    dst = tmp_path / "moda_vault"
    # Copy snippets + forge.toml; explicitly drop any .forge/ so each
    # test starts with zero snapshots (fresh-vault first-call path).
    # v0.2.196 housekeeping drain — also drop `.obsidian` to avoid a
    # symlink loop. The user's dev setup symlinks
    # `.obsidian/plugins/forge-client-obsidian` → the plugin source
    # repo, whose `obsidian_sandbox/sandbox/` subdir is itself a vault
    # that links back, creating an infinite-recursion copy path that
    # killed setup with `shutil.Error: file name too long`. Tests
    # don't read `.obsidian` content, so dropping it is harmless.
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(".forge", ".obsidian"),
    )
    return str(dst)


@pytest.fixture
def run(vault_copy):
    reg = SnippetRegistry()
    reg.scan(vault_copy)
    res = GraphResolver(reg)

    def _run(sid, *args, **inputs):
        snip = res.resolve(sid)
        code = extract_python(snip["body"])
        _, result = exec_python(
            code, inputs, res, args=args,
            vault_path=vault_copy, registry=reg,
            snippet_id=snip["snippet_id"],
        )
        return result

    return _run


def test_go_first_call_uses_sample_state(run):
    # No .forge/edges yet → read_snapshot() is None → sample_state.
    s = run("go")
    assert s is not None
    # sample_state has 25 particles (20 water + 5 ink); go advances it.
    assert len(s.ids) == 25
    assert int((s.types == "water").sum()) == 20
    assert int((s.types == "ink").sum()) == 5
    # move() advances tick once: sample_state tick=0 → 1.
    assert s.tick == 1
    # positions moved off sample_state's starting coords
    assert s.width == 800.0 and s.height == 600.0


def test_go_second_call_uses_snapshot(run):
    s1 = run("go")                 # first: sample_state → tick 1
    s2 = run("go")                 # second: reads s1's snapshot → tick 2
    assert s1.tick == 1
    assert s2.tick == 2            # accumulation: continued, didn't restart
    assert len(s2.ids) == len(s1.ids) == 25
    # particles advanced further — at least one coordinate changed
    moved = (not np.array_equal(s1.xs, s2.xs)) or (not np.array_equal(s1.ys, s2.ys))
    assert moved, "second call did not advance from the first call's state"


def test_go_with_explicit_state_bypasses_snapshot(run):
    run("go")  # create a snapshot so the fallback chain *could* fire
    # Explicit 3-particle state must win over the 25-particle snapshot.
    explicit = make_state(n_water=3, tick=99)
    out = run("go", explicit, 1 / 30, "medium")
    assert len(out.ids) == 3, "explicit state was not used (got snapshot/sample)"
    assert (out.types == "water").all()
    assert out.tick == 100  # 99 + 1 (move advances tick once)
