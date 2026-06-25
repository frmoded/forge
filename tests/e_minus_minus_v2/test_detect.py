"""V2-shape detection tests."""
from forge.e_minus_minus_v2 import detect_v2_shape, extract_emm_body


class TestDetectV2Shape:
  def test_v2_note_detected(self):
    body = """---
type: action
---

# Description

A test note.

# E--

Return 1.
"""
    assert detect_v2_shape(body) is True

  def test_v1_note_not_detected(self):
    body = """---
type: action
---

# English

A test note.

# Python

```python
def compute(context):
  return 1
```
"""
    assert detect_v2_shape(body) is False

  def test_emm_in_frontmatter_ignored(self):
    body = """---
type: action
note: |
  # E-- snippet here for documentation
---

# English

Just a normal V1 note.
"""
    assert detect_v2_shape(body) is False

  def test_extract_emm_body_simple(self):
    body = """---
type: action
---

# Description

A test.

# E--

Let x = 1.
Return x.
"""
    emm = extract_emm_body(body)
    assert "Let x = 1." in emm
    assert "Return x." in emm
    assert "# E--" not in emm
    assert "# Description" not in emm

  def test_extract_emm_body_stops_at_next_heading(self):
    body = """---
type: action
---

# E--

Let x = 1.
Return x.

# Notes

Some trailing content.
"""
    emm = extract_emm_body(body)
    assert "Let x = 1." in emm
    assert "Some trailing" not in emm

  def test_extract_emm_raises_when_missing(self):
    import pytest
    body = "# English\n\nNot a V2 note.\n"
    with pytest.raises(ValueError):
      extract_emm_body(body)
