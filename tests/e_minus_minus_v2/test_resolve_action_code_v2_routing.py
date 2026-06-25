"""V2-routing test for resolve_action_code — confirms V2 notes get
the new transpiler and V1 notes still flow through the legacy path.
"""

import pytest

from forge.core.executor import resolve_action_code


def _mksnip(body, snippet_id="test", meta=None):
  return {"snippet_id": snippet_id, "body": body, "meta": meta or {}}


class TestV2Routing:
  def test_v2_note_yields_v2_transpile(self):
    body = """---
type: action
---

# Description

Return 42.

# E--

Return 42.
"""
    code = resolve_action_code(_mksnip(body))
    # V2 transpiler emits `def compute(context):` with direct Python.
    assert "def compute(context):" in code
    assert "return 42" in code

  def test_v2_with_chip_call(self):
    body = """---
type: action
---

# E--

Let part = Call [[play_at_beats]] with instrument=[[kick]], beats=[1, 3].
[[show_score]] part.
Return part.
"""
    code = resolve_action_code(_mksnip(body))
    assert "play_at_beats(instrument=kick()" in code
    assert "show_score(part)" in code
    assert "return part" in code

  def test_v1_note_falls_through(self):
    # V1 has `# English` (legacy facet name). resolve_action_code's V2
    # detector should return False, falling through to the legacy path,
    # which (with no `# Python`) returns None per its contract.
    body = """---
type: action
---

# English

A V1 note with no E-- heading. Legacy path with no `# Python` heading
returns None per resolve_action_code's contract.
"""
    code = resolve_action_code(_mksnip(body))
    assert code is None
