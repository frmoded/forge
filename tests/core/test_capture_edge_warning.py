"""_capture_edge logs WARNING and skips when the value can't be wire-serialized.

Pre-fix the silent skip hid two missing edges in forge-moda's setup+go
graph (ParticleState and list[Particle] both TypeError'd through
json.dumps) and the only symptom was an empty edges panel. The warning
exists so future surprises surface immediately in the logs.
"""
import logging
import pytest

from forge.core.executor import ForgeContext


def _callee(snippet_id="inner"):
  return {"snippet_id": snippet_id, "meta": {}}


def test_warns_when_value_not_serializable(caplog, tmp_path):
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=str(tmp_path),
    caller_id="outer",
  )
  # Generators trip json.dumps; the codec's dataclass walker doesn't
  # rescue them.
  value = (i for i in range(3))
  with caplog.at_level(logging.WARNING, logger="forge.core.executor"):
    ctx._capture_edge(_callee("inner"), value)

  recs = [r for r in caplog.records
          if r.levelno == logging.WARNING and r.name == "forge.core.executor"]
  assert len(recs) == 1
  msg = recs[0].getMessage()
  assert "snapshot skipped for edge outer→inner" in msg
  assert "generator" in msg


def test_no_warning_when_no_caller_id(caplog, tmp_path):
  """Top-level /compute has no enclosing snippet; capture is a no-op.
  Don't pollute the log with skip warnings in that case."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=str(tmp_path),
    caller_id=None,  # ← the key bit
  )
  with caplog.at_level(logging.WARNING, logger="forge.core.executor"):
    # Even something definitively unserializable shouldn't warn:
    # we early-return before reaching write_snapshot.
    ctx._capture_edge(_callee("inner"), object())
  assert not any(r.levelno == logging.WARNING and r.name == "forge.core.executor"
                 for r in caplog.records)


def test_no_warning_when_no_vault_path(caplog):
  """Raw exec_python in unit tests passes vault_path=None; nothing to
  write, nothing to warn about."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=None,
    caller_id="outer",
  )
  with caplog.at_level(logging.WARNING, logger="forge.core.executor"):
    ctx._capture_edge(_callee(), object())
  assert not any(r.levelno == logging.WARNING and r.name == "forge.core.executor"
                 for r in caplog.records)


def test_serializable_value_writes_snapshot_no_warning(caplog, tmp_path):
  """Sanity: a plain JSON-able value lands on disk and emits no warning."""
  ctx = ForgeContext(
    resolver=None, inputs={},
    vault_path=str(tmp_path),
    caller_id="outer",
  )
  with caplog.at_level(logging.WARNING, logger="forge.core.executor"):
    ctx._capture_edge(_callee("inner"), {"answer": 42})

  # No warning…
  assert not any(r.levelno == logging.WARNING and r.name == "forge.core.executor"
                 for r in caplog.records)
  # …and the snapshot file actually exists.
  snap = tmp_path / ".forge" / "edges" / "outer" / "inner.md"
  assert snap.is_file()
  assert '"answer": 42' in snap.read_text()
