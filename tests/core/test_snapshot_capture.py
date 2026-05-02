"""Phase 2 tests: automatic edge snapshot capture (A7, F1-F3)."""
import os
import yaml
import pytest

from forge.core.executor import exec_python
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT, parse_frontmatter
from forge.core.graph_resolver import GraphResolver
from forge.core.snapshots import snapshot_path, read_snapshot


def _action(body_python):
  return f"# Python\n\n```python\n{body_python}\n```"


def _make_action(snippet_id, body_python):
  vault, bare = snippet_id.split("/", 1)
  return {
    "meta": {"type": "action"},
    "body": _action(body_python),
    "path": "",
    "vault": vault,
    "source": "authoring" if vault == AUTHORING_VAULT else "library",
    "snippet_id": snippet_id,
  }


def _make_data(snippet_id, content_type, body):
  vault, bare = snippet_id.split("/", 1)
  return {
    "meta": {"type": "data", "content_type": content_type},
    "body": body,
    "path": "",
    "vault": vault,
    "source": "authoring" if vault == AUTHORING_VAULT else "library",
    "snippet_id": snippet_id,
  }


def _registry_with(*snippets):
  reg = SnippetRegistry()
  for s in snippets:
    reg._vaults.setdefault(s["vault"], {})
    bare = s["snippet_id"].split("/", 1)[1]
    reg._vaults[s["vault"]][bare] = s
  return reg


def test_simple_edge_creates_snapshot(tmp_path):
  inner = _make_action("authoring/inner", "def compute(context):\n  return 42")
  registry = _registry_with(inner)
  resolver = GraphResolver(registry)

  outer_code = "def compute(context):\n  return context.compute('inner')"
  exec_python(outer_code, {}, resolver, vault_path=str(tmp_path), snippet_id="authoring/outer")

  path = snapshot_path(str(tmp_path), "authoring/outer", "authoring/inner")
  assert os.path.isfile(path)

  snap = read_snapshot(str(tmp_path), "authoring/outer", "authoring/inner")
  meta = snap["meta"]
  assert meta["type"] == "snapshot"
  assert meta["caller"] == "authoring/outer"
  assert meta["callee"] == "authoring/inner"
  assert meta["state"] == "live"
  assert meta["content_type"] == "json"
  assert "captured_at" in meta
  # Body is the JSON-wire-formatted value, fenced.
  assert "42" in snap["body"]


def test_top_level_compute_writes_no_snapshot(tmp_path):
  """Per the brief: top-level /compute (no caller) must not create snapshots."""
  code = "def compute(context):\n  return 7"
  exec_python(code, {}, vault_path=str(tmp_path), snippet_id="authoring/lone")
  edges_root = tmp_path / ".forge" / "edges"
  assert not edges_root.exists() or not any(edges_root.iterdir())


def test_recompute_overwrites_snapshot(tmp_path):
  """A7: 'If a snapshot already exists for that edge, it is overwritten with the latest.'"""
  # Use a side-effect counter to vary the inner result deterministically.
  inner = _make_action("authoring/inner", (
    "def compute(context):\n"
    "  numpy.random.seed(int(numpy.random.rand() * 1000))\n"
    "  return 'first'"
  ))
  registry = _registry_with(inner)
  resolver = GraphResolver(registry)

  outer_code = "def compute(context):\n  return context.compute('inner')"
  exec_python(outer_code, {}, resolver, vault_path=str(tmp_path), snippet_id="authoring/outer")
  first = read_snapshot(str(tmp_path), "authoring/outer", "authoring/inner")
  first_at = first["meta"]["captured_at"]

  # Mutate the inner snippet's return and run again — same edge, fresh capture.
  registry._vaults[AUTHORING_VAULT]["inner"] = _make_action(
    "authoring/inner", "def compute(context):\n  return 'second'"
  )
  exec_python(outer_code, {}, resolver, vault_path=str(tmp_path), snippet_id="authoring/outer")
  second = read_snapshot(str(tmp_path), "authoring/outer", "authoring/inner")
  assert "second" in second["body"]
  assert "first" not in second["body"]
  # captured_at advances or stays the same; either way the body changed.
  assert second["meta"]["captured_at"] >= first_at


def test_compound_ids_become_subdirectory_paths(tmp_path):
  """Per F2: snippet IDs with slashes nest under their namespace."""
  inner = _make_action("forge-core/hello_registry", "def compute(context):\n  return 'hi'")
  registry = _registry_with(inner)
  resolver = GraphResolver(registry)

  outer_code = "def compute(context):\n  return context.compute('forge-core/hello_registry')"
  exec_python(outer_code, {}, resolver, vault_path=str(tmp_path), snippet_id="authoring/outer")

  path = tmp_path / ".forge" / "edges" / "authoring" / "outer" / "forge-core" / "hello_registry.md"
  assert path.exists()


def test_data_snippet_callee_also_captured(tmp_path):
  """Edge capture fires for data callees, not just action callees."""
  data = _make_data("authoring/d", "json", '"the value"')
  registry = _registry_with(data)
  resolver = GraphResolver(registry)

  outer_code = "def compute(context):\n  return context.compute('d')"
  exec_python(outer_code, {}, resolver, vault_path=str(tmp_path), snippet_id="authoring/outer")

  snap = read_snapshot(str(tmp_path), "authoring/outer", "authoring/d")
  assert snap is not None
  assert snap["meta"]["content_type"] == "json"
  assert "the value" in snap["body"]


def test_snapshot_body_is_valid_yaml_frontmatter_plus_fence(tmp_path):
  """The file Forge writes must round-trip through parse_frontmatter cleanly."""
  inner = _make_action("authoring/i", "def compute(context):\n  return {'k': 'v'}")
  registry = _registry_with(inner)
  resolver = GraphResolver(registry)

  outer_code = "def compute(context):\n  return context.compute('i')"
  exec_python(outer_code, {}, resolver, vault_path=str(tmp_path), snippet_id="authoring/outer")

  path = snapshot_path(str(tmp_path), "authoring/outer", "authoring/i")
  with open(path) as f:
    text = f.read()
  meta, body = parse_frontmatter(text)
  assert meta["caller"] == "authoring/outer"
  assert meta["callee"] == "authoring/i"
  assert body.startswith("```")
  assert body.endswith("```")
