"""Tests for hand-authored data snippets and snapshot-type recognition (Phase 1)."""
import pytest
from forge.core.executor import read_data_snippet, exec_python
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
from forge.core.graph_resolver import GraphResolver


def _make_data(meta_extra, body):
  meta = {"type": "data", **meta_extra}
  return {
    "meta": meta,
    "body": body,
    "path": "",
    "vault": AUTHORING_VAULT,
    "source": "authoring",
    "snippet_id": f"{AUTHORING_VAULT}/x",
  }


def test_data_snippet_json_returns_python_value():
  snippet = _make_data({"content_type": "json"}, '{"a": 1, "b": [2, 3]}')
  assert read_data_snippet(snippet) == {"a": 1, "b": [2, 3]}


def test_data_snippet_text_returns_string():
  snippet = _make_data({"content_type": "text"}, "hello world")
  assert read_data_snippet(snippet) == "hello world"


def test_data_snippet_strips_code_fence():
  """Authors often wrap the body in a fenced block for readability."""
  snippet = _make_data({"content_type": "json"}, "```json\n{\"x\": 7}\n```")
  assert read_data_snippet(snippet) == {"x": 7}


def test_data_snippet_missing_content_type_raises():
  snippet = _make_data({}, "anything")
  with pytest.raises(ValueError, match="content_type"):
    read_data_snippet(snippet)


def test_data_snippet_unsupported_content_type_raises():
  snippet = _make_data({"content_type": "made-up-format"}, "stuff")
  with pytest.raises(ValueError, match="unsupported content_type"):
    read_data_snippet(snippet)


def test_snapshot_type_treated_as_data():
  """Snapshots are read like data snippets per F3."""
  snippet = {
    "meta": {"type": "snapshot", "content_type": "json", "caller": "a/x", "callee": "a/y", "state": "live"},
    "body": "42",
    "path": "",
    "vault": AUTHORING_VAULT,
    "source": "authoring",
    "snippet_id": f"{AUTHORING_VAULT}/x",
  }
  assert read_data_snippet(snippet) == 42


def test_data_snippet_resolved_via_context_compute():
  """An action snippet calling context.compute on a data snippet gets the
  deserialized value, not the frontmatter."""
  registry = SnippetRegistry()
  registry._vaults.setdefault(AUTHORING_VAULT, {})
  registry._vaults[AUTHORING_VAULT]["the_data"] = _make_data(
    {"content_type": "json"}, '[10, 20, 30]'
  )
  resolver = GraphResolver(registry)

  caller_code = "def compute(context):\n  return context.compute('the_data')"
  _, result = exec_python(caller_code, {}, resolver, snippet_id="authoring/caller")
  assert result == [10, 20, 30]


def test_action_calling_data_snippet_doesnt_see_frontmatter():
  """Regression — old behavior leaked frontmatter as the return value."""
  registry = SnippetRegistry()
  registry._vaults.setdefault(AUTHORING_VAULT, {})
  registry._vaults[AUTHORING_VAULT]["d"] = _make_data(
    {"content_type": "json", "description": "should not appear"}, '"the body"'
  )
  resolver = GraphResolver(registry)

  caller_code = "def compute(context):\n  return context.compute('d')"
  _, result = exec_python(caller_code, {}, resolver, snippet_id="authoring/caller")
  assert result == "the body"
