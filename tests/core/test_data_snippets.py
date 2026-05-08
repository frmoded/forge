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


def test_data_snippet_markdown_returns_string():
  body = "# Heading\n\nSome **bold** text."
  snippet = _make_data({"content_type": "markdown"}, body)
  assert read_data_snippet(snippet) == body


def test_data_snippet_svg_returns_string():
  body = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
  snippet = _make_data({"content_type": "svg"}, body)
  assert read_data_snippet(snippet) == body


def test_data_snippet_binary_returns_bytes_tuple(tmp_path):
  """Binary content_types load bytes from a sibling asset file referenced by
  content_ref and return (bytes, content_type) per the binary contract."""
  asset = tmp_path / "_assets" / "cat.jpg"
  asset.parent.mkdir(parents=True)
  raw = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
  asset.write_bytes(raw)

  snippet = _make_data({"content_type": "image/jpeg", "content_ref": "_assets/cat.jpg"}, "")
  snippet["vault_path"] = str(tmp_path)

  result = read_data_snippet(snippet)
  assert isinstance(result, tuple) and len(result) == 2
  data, ct = result
  assert data == raw
  assert ct == "image/jpeg"


def test_data_snippet_binary_legacy_jpeg_alias_resolves_to_image_jpeg(tmp_path):
  """Hand-authored vaults using the bare 'jpeg' name still work; the alias
  normalizes to 'image/jpeg' and the tuple's content_type reflects that."""
  asset = tmp_path / "img.jpg"
  asset.write_bytes(b"\xff\xd8\xff")
  snippet = _make_data({"content_type": "jpeg", "content_ref": "img.jpg"}, "")
  snippet["vault_path"] = str(tmp_path)
  data, ct = read_data_snippet(snippet)
  assert data == b"\xff\xd8\xff"
  assert ct == "image/jpeg"


def test_data_snippet_binary_without_content_ref_raises():
  """Binary content_types must use content_ref — body content alone is the
  legacy shape and is no longer accepted."""
  snippet = _make_data({"content_type": "image/jpeg"}, "/9j/4AAQ...")
  with pytest.raises(ValueError, match="requires `content_ref`"):
    read_data_snippet(snippet)


def test_data_snippet_content_ref_with_text_type_raises(tmp_path):
  """content_ref is binary-only; pairing it with a text content_type is a
  config error."""
  asset = tmp_path / "x.txt"
  asset.write_text("hi")
  snippet = _make_data({"content_type": "text", "content_ref": "x.txt"}, "")
  snippet["vault_path"] = str(tmp_path)
  with pytest.raises(ValueError, match="only valid for binary"):
    read_data_snippet(snippet)


def test_data_snippet_content_ref_and_body_mutually_exclusive(tmp_path):
  """A binary snippet must have an empty body when content_ref is set."""
  asset = tmp_path / "x.jpg"
  asset.write_bytes(b"\xff\xd8\xff")
  snippet = _make_data(
    {"content_type": "image/jpeg", "content_ref": "x.jpg"},
    "stray body content",
  )
  snippet["vault_path"] = str(tmp_path)
  with pytest.raises(ValueError, match="mutually exclusive"):
    read_data_snippet(snippet)


def test_data_snippet_content_ref_missing_file_raises(tmp_path):
  snippet = _make_data(
    {"content_type": "image/jpeg", "content_ref": "_assets/missing.jpg"}, "",
  )
  snippet["vault_path"] = str(tmp_path)
  with pytest.raises(FileNotFoundError, match="content_ref"):
    read_data_snippet(snippet)


def test_data_snippet_yaml_returns_native_value():
  snippet = _make_data({"content_type": "yaml"}, "key: value\nlist:\n  - 1\n  - 2\n")
  assert read_data_snippet(snippet) == {"key": "value", "list": [1, 2]}


def test_data_snippet_extracts_under_body_heading():
  """The 'New Snippet' modal generates: # English ... # Body ... fenced payload.
  The executor must extract from under # Body, ignoring the English facet."""
  body = (
    "# English\n"
    "\n"
    "An intent description that mentions {a, b, c} braces as text.\n"
    "\n"
    "# Body\n"
    "\n"
    "```json\n"
    '{"x": 1}\n'
    "```\n"
  )
  snippet = _make_data({"content_type": "json"}, body)
  assert read_data_snippet(snippet) == {"x": 1}


def test_data_snippet_body_heading_case_insensitive():
  body = "# English\nintent\n\n## body\n\n```json\n42\n```"
  snippet = _make_data({"content_type": "json"}, body)
  assert read_data_snippet(snippet) == 42


def test_data_snippet_body_heading_with_no_fence():
  """Markdown payloads under # Body have no surrounding fence — extract as-is."""
  body = "# English\n\nintent\n\n# Body\n\nplain text payload"
  snippet = _make_data({"content_type": "text"}, body)
  assert read_data_snippet(snippet) == "plain text payload"


def test_data_snippet_no_body_heading_falls_back_to_whole_body():
  """Pre-template snippets and snapshots have no headings — keep working."""
  snippet = _make_data({"content_type": "json"}, '{"k": "v"}')
  assert read_data_snippet(snippet) == {"k": "v"}


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
