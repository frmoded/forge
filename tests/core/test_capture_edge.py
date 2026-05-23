"""_capture_edge: tightened C7/A7 contract.

Three behaviors per the constitutional contract:
  1. Serializable return on a capture-eligible snippet → snapshot lands
     at .forge/edges/<caller>/<callee>.md.
  2. Snippet declares `snapshot_capture: false` → capture is skipped
     silently; no snapshot file, no error, no warning.
  3. Non-serializable return on a capture-eligible snippet → raises
     SnapshotCaptureError naming the snippet and the offending type.

Also covers the two early-return cases (no caller, no vault_path) that
predate the C7/A7 tightening: those skip without writing and without
raising regardless of return type, because no edge exists to capture.

Replaces the prior test_capture_edge_warning.py — the
warn-and-skip-on-unserializable behavior is gone; non-serializable
returns now raise unless the snippet has opted out.
"""
import pytest

from forge.core.executor import ForgeContext, SnapshotCaptureError


def _callee(snippet_id="inner", meta=None):
  return {"snippet_id": snippet_id, "meta": meta or {}}


# ---------------------------------------------------------------------------
# The three new contract behaviors
# ---------------------------------------------------------------------------

def test_capture_succeeds_on_serializable_return(tmp_path):
  """Sanity / regression: a serializable value writes a snapshot at the
  expected .forge/edges/<caller>/<callee>.md path. Same path the
  pre-tightening sanity test covered."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=str(tmp_path),
    caller_id="outer",
  )
  ctx._capture_edge(_callee("inner"), {"answer": 42})

  snap = tmp_path / ".forge" / "edges" / "outer" / "inner.md"
  assert snap.is_file()
  assert '"answer": 42' in snap.read_text()


def test_capture_skipped_when_snapshot_capture_false(tmp_path):
  """C7 opt-out: a snippet declaring `snapshot_capture: false` is not
  captured even if its return is opaque. No snapshot file written, no
  exception raised. The author has signaled intent; no warning either."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=str(tmp_path),
    caller_id="outer",
  )
  # An open file handle is genuinely non-serializable (no codec
  # recognizes it). The opt-out should keep this from raising.
  fh = open(tmp_path / "scratch.txt", "w")
  try:
    ctx._capture_edge(
      _callee("inner", meta={"snapshot_capture": False}),
      fh,
    )
  finally:
    fh.close()

  # No snapshot was written.
  snap = tmp_path / ".forge" / "edges" / "outer" / "inner.md"
  assert not snap.exists()


def test_capture_raises_on_unserializable_return_without_opt_out(tmp_path):
  """C7 default: capture-eligible snippet that returns a non-serializable
  value must raise SnapshotCaptureError. Error message names the
  snippet and the offending Python type so the author can decide
  whether to fix the return or declare the opt-out."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=str(tmp_path),
    caller_id="outer",
  )
  value = (i for i in range(3))  # generator — no codec recognizes it
  with pytest.raises(SnapshotCaptureError) as exc_info:
    ctx._capture_edge(_callee("inner"), value)

  msg = str(exc_info.value)
  assert "outer→inner" in msg
  assert "generator" in msg
  # Also surfaces the opt-out hint so the author knows the way out.
  assert "snapshot_capture: false" in msg

  # No partial snapshot file was left behind.
  snap = tmp_path / ".forge" / "edges" / "outer" / "inner.md"
  assert not snap.exists()


# ---------------------------------------------------------------------------
# Early-return cases that predate the tightening — these still hold.
# ---------------------------------------------------------------------------

def test_no_capture_when_no_caller_id(tmp_path):
  """Top-level /compute has no enclosing snippet; capture is a no-op.
  Doesn't matter whether the value is serializable or not — we never
  reach write_snapshot or the opt-out check."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=str(tmp_path),
    caller_id=None,  # ← the key bit
  )
  # Even something definitively unserializable shouldn't raise:
  # we early-return before reaching write_snapshot.
  ctx._capture_edge(_callee("inner"), object())
  snap = tmp_path / ".forge" / "edges"
  assert not snap.exists()


def test_no_capture_when_no_vault_path():
  """Raw exec_python in unit tests passes vault_path=None; nothing to
  write to disk, nothing to raise about."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=None,
    caller_id="outer",
  )
  # No exception even though object() isn't serializable.
  ctx._capture_edge(_callee(), object())
