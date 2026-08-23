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

# Recipe

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

# Recipe

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


class TestRoutingSignalL45:
  """v0.2.252 drain 2026-07-03-1000 §3.3 — plugin's source_layer
  signal short-circuits Recipe parse when Python is the source.

  Driver scenario reproduced: broken Recipe (parse error) + valid
  hand-authored Python. Pre-v0.2.252 the engine parsed Recipe first,
  hit ParseError, blocked execution — even though plugin declared
  python-source. Post-v0.2.252 the engine honors the signal and
  returns Python directly.

  v0.2.286 — routing signal was renamed `source_layer` (from
  `canonical_layer`). The deprecated kwarg still works; a dedicated
  back-compat case at the bottom of this class covers it."""

  def test_source_python_short_circuits_broken_recipe(self):
    # Recipe has a syntax error that would throw ParseError on the
    # V2 parse path. Python is valid.
    body = """---
type: action
python_hash: PPP
---

# Description

Print a friendly greeting.

# Recipe

Call [[print]] with a text="broken".

# Python

```python
def compute(context):
    print("hand-authored python wins")
    return 42
```
"""
    code = resolve_action_code(_mksnip(body), source_layer="python")
    # Plugin declared Python the source facet → engine returns
    # extracted Python directly, no V2 parse attempted.
    assert code is not None
    assert "hand-authored python wins" in code
    assert "return 42" in code

  def test_source_description_now_parses_the_recipe(self):
    # Drain 2026-08-24-2350 — was
    # `test_source_description_short_circuits_to_none`, asserting
    # `code is None` on the reasoning that "Description-source means
    # Recipe + Python are stale".
    #
    # That reasoning was true when it was written and is false now.
    # The plugin's two-hop auto-forge derives the Recipe FROM the
    # Description immediately before running, so on the only path that
    # reaches here with this signal the Recipe is the FRESHEST facet,
    # not the stalest. Drain 2330 traced the driver's
    # "Empty or missing Python code" to exactly this branch; forge-core
    # adjudicated its retirement.
    #
    # Kept as the inverted assertion rather than deleted: the routing
    # signal still arrives (the plugin's belt filters it, but a
    # transitive or third-party caller may not), and what it must do
    # now is parse the Recipe like any other note.
    body = """---
type: action
description_hash: DDD
---

# Description

Just edited description.

# Recipe

Call [[print]] with text="fresh".

# Python

```python
def compute(context):
    return "stale"
```
"""
    code = resolve_action_code(_mksnip(body), source_layer="description")
    assert code is not None, "the 'description' -> None branch is back"
    # The RECIPE was transpiled — not the stale Python facet returned.
    assert "fresh" in code
    assert "return \"stale\"" not in code

  def test_source_recipe_uses_v2_parse_path(self):
    # Recipe-source → engine parses Recipe normally.
    body = """---
type: action
recipe_hash: RRR
---

# Recipe

Return 42.
"""
    code = resolve_action_code(_mksnip(body), source_layer="recipe")
    assert code is not None
    assert "return 42" in code

  def test_source_synced_preserves_existing_behavior(self):
    # synced → same as pre-v0.2.252 behavior (V2 parse if V2 note).
    body = """---
type: action
---

# Recipe

Return 42.
"""
    code = resolve_action_code(_mksnip(body), source_layer="synced")
    assert code is not None
    assert "return 42" in code

  def test_no_source_layer_preserves_pre_v0_2_252_behavior(self):
    # Backward compat: when caller doesn't pass source_layer, the
    # V2 parse path fires as before. Regression check for existing
    # callers (moda dispatch, legacy plugin state).
    body = """---
type: action
---

# Recipe

Return 42.
"""
    code = resolve_action_code(_mksnip(body))
    assert code is not None
    assert "return 42" in code

  def test_canonical_layer_kwarg_still_works_v0_2_286(self):
    # v0.2.286 back-compat: the previous kwarg name `canonical_layer`
    # must still route to the same short-circuit as the new
    # `source_layer`. Plugin's bundled engine may be older than the
    # forge repo during a rolling upgrade; this guarantee lets the
    # plugin migrate on its own cadence.
    body = """---
type: action
python_hash: PPP
---

# Description

Just some words.

# Recipe

Call [[print]] with a text="broken".

# Python

```python
def compute(context):
    return "legacy-kwarg"
```
"""
    code = resolve_action_code(_mksnip(body), canonical_layer="python")
    assert code is not None
    assert "legacy-kwarg" in code
