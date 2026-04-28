from pathlib import Path
import pytest
from forge.builtins.loader import load_builtin_vault
from forge.core.executor import extract_python, exec_python
from forge.core.snippet_registry import SnippetRegistry
from forge.core.graph_resolver import GraphResolver


class _FakeContext:
  """Lightweight stand-in for ForgeContext that records execute() calls
  and returns canned per-snippet responses. Exercises orchestration logic
  without hitting the real sub-snippets."""

  def __init__(self, vault_path, vault_name, version, responses):
    self.vault_path = vault_path
    self._kwargs = {"vault_name": vault_name, "version": version}
    self._responses = responses
    self.calls = []

  def get(self, key, default=None):
    return self._kwargs.get(key, default)

  def __getitem__(self, key):
    return self._kwargs[key]

  def execute(self, snippet_id, **kwargs):
    self.calls.append((snippet_id, kwargs))
    return self._responses.get(snippet_id)


def _orchestrator_callable():
  snippets = load_builtin_vault()
  install = next(s for s in snippets if s["snippet_id"] == "forge/install")
  code = extract_python(install["body"])
  ns = {"__builtins__": __builtins__}
  exec(compile(code, "<install>", "exec"), ns)
  return ns["run"]


def test_orchestrator_calls_subsnippets_in_order():
  run = _orchestrator_callable()
  responses = {
    "forge/registry/lookup": {
      "tarball": "https://example.com/x.tar.gz",
      "sha256": "f" * 64,
      "version": "0.2.0",
    },
    "forge/registry/fetch": "/cache/path/x.tar.gz",
    "forge/vault/extract": {"vault_dir": "/v/forge-core", "manifest": object()},
    "forge/manifest/add_dep": object(),
    "forge/registry/refresh": {"refreshed": True},
  }
  ctx = _FakeContext("/v", "forge-core", None, responses)

  result = run(ctx)
  call_ids = [c[0] for c in ctx.calls]
  assert call_ids == [
    "forge/registry/lookup",
    "forge/registry/fetch",
    "forge/vault/extract",
    "forge/manifest/add_dep",
    "forge/registry/refresh",
  ]
  assert result["vault_name"] == "forge-core"
  assert result["version"] == "0.2.0"
  assert "[[forge-core/" in result["message"]


def test_orchestrator_wires_outputs_into_inputs():
  run = _orchestrator_callable()
  responses = {
    "forge/registry/lookup": {
      "tarball": "https://example.com/x.tar.gz",
      "sha256": "abc",
      "version": "0.3.0",
    },
    "forge/registry/fetch": "/cache/abc.tar.gz",
    "forge/vault/extract": {"vault_dir": "/v/lib", "manifest": object()},
    "forge/manifest/add_dep": object(),
    "forge/registry/refresh": {},
  }
  ctx = _FakeContext("/my-vault", "lib", "0.3.0", responses)
  run(ctx)

  by_id = {sid: kw for sid, kw in ctx.calls}

  assert by_id["forge/registry/lookup"] == {"vault_name": "lib", "version": "0.3.0"}
  assert by_id["forge/registry/fetch"] == {
    "tarball_url": "https://example.com/x.tar.gz",
    "expected_sha256": "abc",
  }
  assert by_id["forge/vault/extract"] == {
    "tarball_path": "/cache/abc.tar.gz",
    "target_dir": str(Path("/my-vault") / "lib"),
  }
  assert by_id["forge/manifest/add_dep"] == {
    "authoring_vault_dir": "/my-vault",
    "dep_name": "lib",
    "dep_version": "0.3.0",
  }
  assert by_id["forge/registry/refresh"] == {}


def test_orchestrator_passes_through_optional_version():
  run = _orchestrator_callable()
  responses = {
    "forge/registry/lookup": {"tarball": "https://x", "sha256": "0", "version": "9.9.9"},
    "forge/registry/fetch": "/p",
    "forge/vault/extract": {"vault_dir": "/v/n", "manifest": object()},
    "forge/manifest/add_dep": object(),
    "forge/registry/refresh": {},
  }
  ctx = _FakeContext("/v", "n", None, responses)
  result = run(ctx)
  by_id = {sid: kw for sid, kw in ctx.calls}
  assert by_id["forge/registry/lookup"]["version"] is None
  # add_dep records the *resolved* version from the lookup result
  assert by_id["forge/manifest/add_dep"]["dep_version"] == "9.9.9"
  assert result["vault_name"] == "n"
  assert result["version"] == "9.9.9"


def test_orchestrator_requires_vault_path():
  run = _orchestrator_callable()
  ctx = _FakeContext(None, "forge-core", None, {})
  with pytest.raises(RuntimeError, match="vault_path"):
    run(ctx)
