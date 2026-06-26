"""V2 data-note shape regression test.

Per v2-spec §3.4: data notes declare their payload format via
`body_format:` in frontmatter (e.g., `json`, `yaml`, `musicxml`). The
pre-V2 engine used `content_type:` for the same purpose. Tutorial's
colors.md migrated to V2 (`body_format: json`) in v0.2.167; the
engine's read_data_snippet still expected `content_type:` only —
runtime crashed with "data snippet 'colors' has no content_type in
frontmatter" the first time an action note tried to consume the data.

This drain's tutorial smoke ran transpile-only (resolve_action_code)
which doesn't touch the data-read path. Adding exec-level coverage
catches the read_data_snippet → body_format gap.
"""

import textwrap

import pytest

from forge.core.executor import read_data_snippet


def _snippet(body, meta):
  return {"snippet_id": "colors", "body": body, "meta": meta}


class TestV2DataNoteBodyFormat:
  def test_v2_json_via_body_format(self):
    """V2 spec §3.4 — body_format: json + # Body section."""
    body = textwrap.dedent("""\
      # Description

      Test note.

      # Body

      ["red", "green", "blue"]
    """)
    snip = _snippet(body, meta={"type": "data", "body_format": "json"})
    result = read_data_snippet(snip)
    assert result == ["red", "green", "blue"]

  def test_v2_json_via_body_format_with_fence(self):
    """V2 spec §3.4 with a markdown ```json code fence around the payload."""
    body = textwrap.dedent("""\
      # Body

      ```json
      ["red", "green", "blue"]
      ```
    """)
    snip = _snippet(body, meta={"type": "data", "body_format": "json"})
    result = read_data_snippet(snip)
    assert result == ["red", "green", "blue"]

  def test_v1_content_type_still_works(self):
    """V1 contract preserved — content_type continues to work."""
    body = '["red", "green", "blue"]\n'
    snip = _snippet(body, meta={"type": "data", "content_type": "json"})
    result = read_data_snippet(snip)
    assert result == ["red", "green", "blue"]

  def test_neither_field_raises(self):
    snip = _snippet("[1, 2]", meta={"type": "data"})
    with pytest.raises(ValueError, match="no content_type"):
      read_data_snippet(snip)
