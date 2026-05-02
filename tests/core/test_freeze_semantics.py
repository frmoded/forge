"""Phase 3 tests: edge freeze short-circuits compute (A8, A9, F4, F7, F8)."""
import pytest

from forge.core.executor import exec_python
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
from forge.core.graph_resolver import GraphResolver
from forge.core.snapshots import read_snapshot, set_snapshot_state


def _action(snippet_id, body_python):
  vault = snippet_id.split("/", 1)[0]
  return {
    "meta": {"type": "action"},
    "body": f"# Python\n\n```python\n{body_python}\n```",
    "path": "",
    "vault": vault,
    "source": "authoring",
    "snippet_id": snippet_id,
  }


def _registry_with(*snippets):
  reg = SnippetRegistry()
  for s in snippets:
    reg._vaults.setdefault(s["vault"], {})
    bare = s["snippet_id"].split("/", 1)[1]
    reg._vaults[s["vault"]][bare] = s
  return reg


def _run(outer_code, vault_path, registry):
  return exec_python(
    outer_code, {}, GraphResolver(registry),
    vault_path=str(vault_path),
    snippet_id="authoring/outer",
  )


def test_frozen_edge_returns_snapshot_without_invoking_callee(tmp_path):
  inner = _action("authoring/inner", "def compute(context):\n  raise RuntimeError('should not run')")
  registry = _registry_with(_action("authoring/inner", "def compute(context):\n  return 'live-value'"))
  outer_code = "def compute(context):\n  return context.compute('inner')"

  # First call captures the live snapshot.
  _, result1 = _run(outer_code, tmp_path, registry)
  assert result1 == "live-value"

  # Freeze the edge.
  set_snapshot_state(str(tmp_path), "authoring/outer", "authoring/inner", "frozen")

  # Replace inner with a snippet that would raise if invoked.
  registry._vaults[AUTHORING_VAULT]["inner"] = inner
  _, result2 = _run(outer_code, tmp_path, registry)

  # Frozen edge: returns the prior snapshot, never enters inner.
  assert result2 == "live-value"


def test_unfreezing_recomputes_and_overwrites(tmp_path):
  registry = _registry_with(_action("authoring/inner", "def compute(context):\n  return 'v1'"))
  outer = "def compute(context):\n  return context.compute('inner')"
  _run(outer, tmp_path, registry)

  set_snapshot_state(str(tmp_path), "authoring/outer", "authoring/inner", "frozen")

  # While frozen, mutate inner — frozen pin holds the old value.
  registry._vaults[AUTHORING_VAULT]["inner"] = _action(
    "authoring/inner", "def compute(context):\n  return 'v2'"
  )
  _, result_frozen = _run(outer, tmp_path, registry)
  assert result_frozen == "v1"

  # Unfreeze and re-run — recompute, snapshot overwritten with the new value.
  set_snapshot_state(str(tmp_path), "authoring/outer", "authoring/inner", "live")
  _, result_live = _run(outer, tmp_path, registry)
  assert result_live == "v2"
  snap = read_snapshot(str(tmp_path), "authoring/outer", "authoring/inner")
  assert snap["meta"]["state"] == "live"
  assert "v2" in snap["body"]


def test_transitive_freeze_short_circuits_subgraph(tmp_path):
  """X→Y frozen with Y→Z dep: computing X must not invoke Y NOR Z (F8)."""
  z = _action("authoring/z", "def compute(context):\n  return 'z-original'")
  y = _action(
    "authoring/y",
    "def compute(context):\n  return 'y-uses-' + context.compute('z')",
  )
  registry = _registry_with(z, y)
  outer = "def compute(context):\n  return context.compute('y')"

  # Initial run captures both Y→Z and outer→Y.
  _, first = _run(outer, tmp_path, registry)
  assert first == "y-uses-z-original"

  # Freeze outer→Y. Replace BOTH Y and Z with snippets that raise if invoked.
  set_snapshot_state(str(tmp_path), "authoring/outer", "authoring/y", "frozen")
  registry._vaults[AUTHORING_VAULT]["y"] = _action(
    "authoring/y", "def compute(context):\n  raise RuntimeError('y should be frozen')"
  )
  registry._vaults[AUTHORING_VAULT]["z"] = _action(
    "authoring/z", "def compute(context):\n  raise RuntimeError('z must not be reached')"
  )

  _, frozen_result = _run(outer, tmp_path, registry)
  # Y returned its frozen value; Z was never reached because Y wasn't entered.
  assert frozen_result == "y-uses-z-original"


def test_per_edge_granularity_different_callers(tmp_path):
  """A→C frozen, B→C live: C is fresh from B but pinned from A (F7)."""
  c = _action("authoring/c", "def compute(context):\n  return 'c-original'")
  registry = _registry_with(c)

  # Run C from caller "a" and from caller "b" so both edges are captured.
  exec_python(
    "def compute(context):\n  return context.compute('c')",
    {}, GraphResolver(registry),
    vault_path=str(tmp_path), snippet_id="authoring/a",
  )
  exec_python(
    "def compute(context):\n  return context.compute('c')",
    {}, GraphResolver(registry),
    vault_path=str(tmp_path), snippet_id="authoring/b",
  )

  # Freeze a→c only.
  set_snapshot_state(str(tmp_path), "authoring/a", "authoring/c", "frozen")

  # Now mutate C.
  registry._vaults[AUTHORING_VAULT]["c"] = _action(
    "authoring/c", "def compute(context):\n  return 'c-updated'"
  )

  _, from_a = exec_python(
    "def compute(context):\n  return context.compute('c')",
    {}, GraphResolver(registry),
    vault_path=str(tmp_path), snippet_id="authoring/a",
  )
  _, from_b = exec_python(
    "def compute(context):\n  return context.compute('c')",
    {}, GraphResolver(registry),
    vault_path=str(tmp_path), snippet_id="authoring/b",
  )

  assert from_a == "c-original"  # frozen pin
  assert from_b == "c-updated"   # live, picks up new value
