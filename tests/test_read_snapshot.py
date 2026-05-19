"""Engine tests for ForgeContext.read_snapshot() (option-A semantics).

read_snapshot scans the snippet's OWN outbound edge directory
`<vault>/.forge/edges/<self_id>/**`, picks the newest snapshot by
(captured_at, file mtime), and returns the deserialized body — or None.
Independent of freeze; self-only; skips malformed files.
"""
import os
import time

from forge.core.executor import ForgeContext


def _ctx(vault, self_id):
    # resolver / inputs / registry are unused by read_snapshot.
    return ForgeContext(None, {}, vault_path=vault, caller_id=self_id)


def _write_snapshot(vault, caller_id, callee_id, json_body,
                    captured_at="2026-01-01T00:00:00Z",
                    content_type="json", snap_type="snapshot",
                    state="live"):
    path = os.path.join(vault, ".forge", "edges", caller_id,
                        callee_id + ".md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fm = (
        f"type: {snap_type}\n"
        f"caller: {caller_id}\n"
        f"callee: {callee_id}\n"
        f"state: {state}\n"
        f"captured_at: {captured_at}\n"
        f"content_type: {content_type}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\n{fm}---\n\n```{content_type}\n{json_body}\n```\n")
    return path


def test_none_when_no_edges_dir(tmp_path):
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() is None


def test_none_when_no_self_snapshot_but_others_exist(tmp_path):
    # A snapshot exists, but under a DIFFERENT snippet's outbound dir.
    _write_snapshot(str(tmp_path), "authoring/other", "authoring/x",
                    '{"v": 1}')
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() is None


def test_returns_value_when_one_snapshot(tmp_path):
    _write_snapshot(str(tmp_path), "authoring/go",
                    "authoring/ask_water_particles", '{"v": 42}')
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() == {"v": 42}


def test_returns_latest_by_captured_at(tmp_path):
    _write_snapshot(str(tmp_path), "authoring/go", "authoring/a",
                    '{"v": "old"}', captured_at="2026-01-01T00:00:00Z")
    _write_snapshot(str(tmp_path), "authoring/go", "authoring/b",
                    '{"v": "new"}', captured_at="2026-06-01T12:00:00Z")
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() == {"v": "new"}


def test_mtime_breaks_captured_at_tie(tmp_path):
    # Same 1-second captured_at (the real-world go() case): the file
    # written LAST (later mtime) wins — the terminal callee == go's
    # return for a pass-through.
    ts = "2026-03-03T03:03:03Z"
    _write_snapshot(str(tmp_path), "authoring/go",
                    "authoring/ask_all_particles", '{"v": "intermediate"}',
                    captured_at=ts)
    time.sleep(0.02)
    _write_snapshot(str(tmp_path), "authoring/go",
                    "authoring/ask_water_particles", '{"v": "return"}',
                    captured_at=ts)
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() == {"v": "return"}


def test_skips_malformed_falls_back_to_next_newest(tmp_path):
    _write_snapshot(str(tmp_path), "authoring/go", "authoring/good",
                    '{"v": "good"}', captured_at="2026-01-01T00:00:00Z")
    # Newer file, but its body is not valid JSON -> skipped, older
    # valid one returned.
    time.sleep(0.02)
    _write_snapshot(str(tmp_path), "authoring/go", "authoring/bad",
                    "{not: valid json", captured_at="2026-09-09T09:09:09Z")
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() == {"v": "good"}


def test_garbage_frontmatter_is_skipped(tmp_path):
    path = os.path.join(str(tmp_path), ".forge", "edges", "authoring/go",
                        "authoring/junk.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("not a snapshot at all, no frontmatter\n")
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() is None


def test_independent_of_freeze_state(tmp_path):
    # state: frozen must still be readable — read_snapshot ignores F1-F9.
    _write_snapshot(str(tmp_path), "authoring/go", "authoring/c",
                    '{"v": "frozen-ok"}', state="frozen")
    assert _ctx(str(tmp_path), "authoring/go").read_snapshot() == {
        "v": "frozen-ok"}


def test_cross_vault_no_crosstalk(tmp_path):
    va = tmp_path / "vault_a"
    vb = tmp_path / "vault_b"
    _write_snapshot(str(va), "authoring/go", "authoring/x", '{"v": "A"}')
    _write_snapshot(str(vb), "music/song", "music/phrase", '{"v": "B"}')
    assert _ctx(str(va), "authoring/go").read_snapshot() == {"v": "A"}
    assert _ctx(str(vb), "music/song").read_snapshot() == {"v": "B"}
    # A reading with B's self_id (not present in A) -> None
    assert _ctx(str(va), "music/song").read_snapshot() is None


def test_none_when_caller_id_or_vault_missing(tmp_path):
    assert ForgeContext(None, {}, vault_path=str(tmp_path),
                        caller_id=None).read_snapshot() is None
    assert ForgeContext(None, {}, vault_path=None,
                        caller_id="authoring/go").read_snapshot() is None
