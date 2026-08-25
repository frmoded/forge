"""Drain 2026-08-25-0110 — the engine reads the note's own `source_facet`.

WHY THIS EXISTS. Drain 2390 found that a note the PLUGIN calls
python-canonical had no engine-side protection at all: three of the four
shipped notes declaring `source_facet: python` executed different code
depending on which button was pressed, and for all three the no-layer
path raised SlotCacheMissError — an LLM call, then Recipe code, in place
of the cohort's hand-edited Python.

The escalation asked for an engine-side guarantee. forge-core adjudicated
the shape: NOT reviving `edit_mode`, NOT new plugin writes to cohort
notes. The signal already lives in the note — `source_facet` frontmatter,
which the plugin maintains and the shipped notes already carry. The
engine simply never read it (`source_facet` occurrences in executor.py
before this drain: 0).

PRECEDENCE, unchanged from 2370/2390: an explicit caller-passed layer
always wins. The frontmatter is only the DEFAULT for callers that pass
nothing — the strip, Cmd-P, MCP, scripts, transitive paths, and whatever
comes next.

NO `None`-returning branch comes back. 2350's retirement stands: only
`python` short-circuits, and only when there is Python to serve.
"""

import pytest

from forge.core.executor import resolve_action_code
from forge.core.slot_cache import SlotCacheMissError
from forge.core.snippet_registry import parse_frontmatter

NESTED_ID = "authoring/divergent"

# The exposed shape, verbatim: a hand-edited `# Python` and a Recipe
# that disagrees with it, so the answer is a VALUE and not an inference.
# 42 = the hand edit, 7 = the Recipe.
DIVERGENT = """---
type: action
source_facet: python
---

# Description

Return a number.

# Recipe

Return 7.

# Python

```python
def compute(context):
    return 42
```
"""


def _snip(body, meta=None):
  """Build the snippet dict the way the registry does.

  `meta` is PARSED FROM THE FRONTMATTER, not hand-fed. Hand-feeding
  `source_facet` would let this suite pass on a note whose frontmatter
  the real parser never surfaces — which is the whole thing under test.
  """
  parsed, _rest = parse_frontmatter(body)
  parsed.setdefault("type", "action")
  if meta:
    parsed.update(meta)
  return {"snippet_id": NESTED_ID, "body": body, "meta": parsed}


def test_no_layer_on_a_python_note_serves_the_hand_edit():
  """THE GUARD. Before this drain the same call transpiled the Recipe."""
  code = resolve_action_code(_snip(DIVERGENT))
  assert code is not None
  assert "return 42" in code
  assert "return 7" not in code


def test_no_layer_on_a_python_note_costs_no_llm_call():
  """The three exposed music-theory notes raised SlotCacheMissError on
  this path, which is a /resolve-slot round trip and a bill. Serving the
  Python cannot raise it."""
  slotted = DIVERGENT.replace("Return 7.", "Let x = {{ a random float }}.\nReturn x.")
  code = resolve_action_code(_snip(slotted))
  assert "return 42" in code


def test_an_explicit_layer_still_wins():
  """Precedence, same as 2370/2390: the branches that know keep
  deciding. A caller that says 'recipe' gets the Recipe even though the
  frontmatter says python."""
  code = resolve_action_code(_snip(DIVERGENT), canonical_layer="recipe")
  assert "return 7" in code
  assert "return 42" not in code


def test_python_frontmatter_with_no_python_heading_is_unchanged():
  """describe_forge's shape, and the reason this is a fall-through and
  not a short-circuit.

  That note declares `source_facet: python` and has NO `# Python`
  heading at all (extract_python -> None). 2390 measured it as the one
  shipped python-canonical note that was NOT exposed, precisely because
  both paths already agreed. It must keep agreeing."""
  no_python = DIVERGENT.split("# Python")[0]
  before = resolve_action_code(_snip(no_python), canonical_layer="recipe")
  after = resolve_action_code(_snip(no_python))
  assert after == before
  assert "return 7" in after


# --- non-vacuity: every other facet value behaves exactly as before ---

@pytest.mark.parametrize("facet_line", [
  "source_facet: description",
  "source_facet: recipe",
  "source_facet: synced",
  "source_facet: nonsense",
  "",  # absent
])
def test_other_source_facet_values_are_byte_identical_to_today(facet_line):
  """The change must be invisible to everything that is not
  python-canonical. Compared against the SAME note routed with an
  explicit 'recipe', which is the behaviour the default had before."""
  body = DIVERGENT.replace("source_facet: python", facet_line)
  assert resolve_action_code(_snip(body)) == resolve_action_code(
    _snip(body), canonical_layer="recipe")


def test_description_does_not_return_none():
  """2350's retirement stands. A `source_facet: description` note must
  transpile its Recipe, not resurrect the branch that returned None and
  produced the driver's empty-code error."""
  body = DIVERGENT.replace("source_facet: python", "source_facet: description")
  code = resolve_action_code(_snip(body))
  assert code is not None, "the 'description' -> None branch is back"
  assert "return 7" in code


def test_edit_mode_still_works_for_whoever_typed_it():
  """Left as-is this drain. Retiring it is its own cleanup."""
  body = DIVERGENT.replace("source_facet: python", "edit_mode: python")
  code = resolve_action_code(
    _snip(body, meta={"type": "action", "edit_mode": "python"}))
  assert "return 42" in code
