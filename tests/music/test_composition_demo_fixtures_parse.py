"""Every composition-primitive demo note's Recipe must actually parse.

CW-forge-music-lib-add-melodic-line-tier-1 (drain 2026-08-05-1100).

WHY THIS FILE EXISTS
--------------------
Drain 2026-08-05-0730 shipped `exercises/rhythmic_line_demo.md` with a
Recipe that has never parsed:

    Let patterns = {"swing": [...], "waltz": [...]}.

E-- has no dict literal. `{` is not a lexable character outside a
`{{ ... }}` code slot, so that line fails at tokenization with
`unexpected char '{'`. The note has been sitting in the vault looking
correct since it was written.

Nothing caught it because a fixture note is data, not code: the engine
suite never parsed it, and the only path that would have — a human
clicking Forge in Obsidian — was listed as driver-deferred smoke in
both drains. Two drains in a row deferred the one step that runs the
thing, so the failure survived being "verified" twice.

The drain 1100 prompt asked for the same broken shape again, plus
subscripting (`contours[choice]["pitches"]`), which is also not E--.
Writing the fixture by copying the previous one would have shipped a
second unparseable note.

So: this test parses the real files, in the vault, as they sit. The
correct idiom is to put the whole lookup inside a slot — slot contents
are Python and take dicts and subscripts freely.
"""
import pathlib

import pytest

from forge.recipe import parser

VAULT = pathlib.Path(__file__).resolve().parents[3] / "forge-music"

DEMOS = [
  "exercises/rhythmic_line_demo.md",
  "exercises/melodic_line_demo.md",
  # Drain 2026-08-05-1800 — chord_stream. Its prompt sketched the same
  # bare multi-line dict that broke drain 0730; the shipped fixture
  # uses the slot-wrapped idiom this file exists to enforce.
  "exercises/chord_stream_demo.md",
]


def recipe_of(path):
  body = path.read_text(encoding="utf-8")
  assert "# Recipe" in body, f"{path} has no # Recipe facet"
  return body.split("# Recipe", 1)[1].strip()


@pytest.mark.parametrize("rel", DEMOS)
def test_demo_recipe_parses(rel):
  path = VAULT / rel
  if not path.exists():
    pytest.skip(f"{path} not present — forge-music not checked out beside forge")
  try:
    parser.parse(recipe_of(path))
  except Exception as exc:
    pytest.fail(
      f"{rel} does not parse: {type(exc).__name__}: {exc}\n"
      "E-- has no dict literal and no subscript. Put the lookup inside "
      "a {{ ... }} code slot, whose contents are Python."
    )


@pytest.mark.parametrize("rel", DEMOS)
def test_demo_recipe_has_no_bare_dict_literal(rel):
  """The specific shape that broke, named so the failure explains itself.

  `test_demo_recipe_parses` already covers this, but its message would
  be the tokenizer's. A note author who re-introduces a bare dict wants
  to be told what to do instead, not where the lexer gave up.
  """
  path = VAULT / rel
  if not path.exists():
    pytest.skip(f"{path} not present")
  for lineno, line in enumerate(recipe_of(path).split("\n"), 1):
    stripped = line.strip()
    if not stripped.startswith("Let ") or "{{" in stripped:
      continue
    assert "{" not in stripped, (
      f"{rel}:{lineno} uses a dict literal outside a code slot. E-- has "
      "no dict syntax — move it inside {{ ... }}."
    )


def test_the_parser_really_does_reject_a_bare_dict():
  """Pins the premise the other two tests rest on.

  If E-- ever gains dict literals, this fails, and whoever added them
  gets told that the guard above is now over-strict — rather than the
  guard quietly enforcing a restriction the language no longer has.
  """
  with pytest.raises(Exception, match=r"unexpected char '\{'"):
    parser.parse('Let d = {"a": 1}.\nReturn d.')


def test_a_slot_wrapped_dict_is_accepted():
  # The recommended idiom, pinned so the advice in the failure messages
  # above cannot go stale.
  parser.parse('Let p = {{ {"a": ["q"]}[choice] }}.\nReturn p.')
