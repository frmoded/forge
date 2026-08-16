"""Drain 2026-08-14-2230 — bundle-time `inputs:` stamping pass.

The plugin's reactive stamper is EDIT-triggered, so a note written to disk by a
drain and never opened in a plugin-loaded session never receives its `inputs:`
frontmatter. Drain 2210 found the two forge-tutorial notes in exactly that
state, while `music-core/pitched_line.md` — authored live — has it.

This pass is the complementary bundle-time half. It does NOT replace the live
stamper, and it has nothing to do with the run button: drain 2210 established
that `forge-button-gate-core.ts` reads `type` only.

Tests assert against `derive_inputs_from_recipe`'s ACTUAL output rather than a
hardcoded list, so they cannot silently drift from the deriver.
"""
from pathlib import Path

import pytest

from forge.recipe.parser import derive_inputs_from_recipe

from scripts.stamp_inputs import main, stamp_note, stamp_vault  # noqa: E402

_INPUT_NOTE = """---
type: action
---

# Description

Takes a word.

# Recipe

Input word: str = "hooray".
Return word + "!".
"""

_LET_ONLY_NOTE = """---
type: action
---

# Description

No Input statements here.

# Recipe

Let x: int = 5.
Return x + 1.
"""

_NO_RECIPE_NOTE = """---
type: vanilla
---

# Description

Just prose.
"""


def _recipe_of(text: str) -> str:
  return text.split("# Recipe\n", 1)[1] if "# Recipe\n" in text else ""


def _expected_names(text: str) -> list[str]:
  """The deriver's own answer — never a hardcoded expectation."""
  return [d.name for d in derive_inputs_from_recipe(_recipe_of(text))]


def test_stamps_a_note_that_has_an_input_declaration(tmp_path: Path):
  p = tmp_path / "excited.md"
  p.write_text(_INPUT_NOTE)

  changed = stamp_note(p)

  assert changed is True
  out = p.read_text()
  expected = _expected_names(_INPUT_NOTE)
  assert expected, "fixture should derive at least one input"
  for name in expected:
    assert name in out
  assert "inputs:" in out


def test_stamped_value_equals_the_derivers_answer(tmp_path: Path):
  """§5 — assert equality against the real function, not a literal."""
  p = tmp_path / "excited.md"
  p.write_text(_INPUT_NOTE)
  stamp_note(p)

  import re

  m = re.search(r"^inputs:\n((?:  - .*\n)+)", p.read_text(), re.M)
  assert m, p.read_text()
  written = [line.strip()[2:].strip() for line in m.group(1).splitlines()]
  assert written == _expected_names(_INPUT_NOTE)


def test_is_idempotent(tmp_path: Path):
  """§5 — running twice produces the same file and reports no change."""
  p = tmp_path / "excited.md"
  p.write_text(_INPUT_NOTE)

  assert stamp_note(p) is True
  first = p.read_text()
  assert stamp_note(p) is False, "second run should be a no-op"
  assert p.read_text() == first


def test_let_only_note_is_untouched(tmp_path: Path):
  """§4 — scope is notes WITH an Input declaration. Legacy `Let`-only
  inference stays exactly as it is today: this pass leaves it alone."""
  p = tmp_path / "letonly.md"
  p.write_text(_LET_ONLY_NOTE)
  before = p.read_text()

  assert stamp_note(p) is False
  assert p.read_text() == before


def test_note_without_a_recipe_is_untouched(tmp_path: Path):
  p = tmp_path / "vanilla.md"
  p.write_text(_NO_RECIPE_NOTE)
  before = p.read_text()

  assert stamp_note(p) is False
  assert p.read_text() == before


def test_existing_correct_inputs_are_not_rewritten(tmp_path: Path):
  p = tmp_path / "already.md"
  p.write_text(_INPUT_NOTE)
  stamp_note(p)
  stamped = p.read_text()

  # A fresh pass over an already-correct note must report no change.
  assert stamp_note(p) is False
  assert p.read_text() == stamped


def test_wrong_existing_inputs_are_corrected(tmp_path: Path):
  """The pass corrects, not just fills — a stale value must be fixed."""
  p = tmp_path / "stale.md"
  p.write_text(_INPUT_NOTE.replace("type: action\n", "type: action\ninputs:\n  - wrongname\n"))

  assert stamp_note(p) is True
  out = p.read_text()
  assert "wrongname" not in out
  for name in _expected_names(_INPUT_NOTE):
    assert name in out


def test_stamp_vault_walks_recursively(tmp_path: Path):
  (tmp_path / "a" / "b").mkdir(parents=True)
  (tmp_path / "a" / "one.md").write_text(_INPUT_NOTE)
  (tmp_path / "a" / "b" / "two.md").write_text(_INPUT_NOTE)
  (tmp_path / "a" / "skip.md").write_text(_LET_ONLY_NOTE)

  changed = stamp_vault(tmp_path)

  assert sorted(p.name for p in changed) == ["one.md", "two.md"]
  # Idempotent at the vault level too.
  assert stamp_vault(tmp_path) == []


# --------------------------------------------------------------- --check


"""Drain 2026-08-16-0910 — `--check` must not WRITE.

Found while wiring the pass into the release preflight: `--check` only
changed the printed verb and the exit code. `stamp_vault` wrote either
way, so the check mutated the very vault it was inspecting — the first
run "failed" and silently fixed the drift, and a re-run passed. As a
release gate that means every cut rewrites bundled content, and a CI
failure disappears on retry with an unexplained working-tree change.
"""


def test_check_mode_reports_drift_without_writing(tmp_path: Path):
  p = tmp_path / "stale.md"
  drifted = _INPUT_NOTE.replace("type: action\n", "type: action\ninputs:\n  - wrongname\n")
  p.write_text(drifted)

  needs = stamp_note(p, write=False)

  assert needs is True, "a drifted note must still be REPORTED as needing a stamp"
  assert p.read_text() == drifted, "--check must leave the file byte-identical"


def test_check_mode_on_a_correct_note_reports_no_change(tmp_path: Path):
  p = tmp_path / "ok.md"
  p.write_text(_INPUT_NOTE)
  stamp_note(p)  # bring it up to date for real
  stamped = p.read_text()

  assert stamp_note(p, write=False) is False
  assert p.read_text() == stamped


def test_stamp_vault_check_mode_writes_nothing(tmp_path: Path):
  (tmp_path / "a").mkdir()
  drifted = _INPUT_NOTE.replace("type: action\n", "type: action\ninputs:\n  - wrongname\n")
  (tmp_path / "a" / "one.md").write_text(drifted)

  found = stamp_vault(tmp_path, write=False)

  assert [p.name for p in found] == ["one.md"]
  assert (tmp_path / "a" / "one.md").read_text() == drifted


def test_main_check_exits_1_and_leaves_the_vault_untouched(tmp_path: Path):
  p = tmp_path / "stale.md"
  drifted = _INPUT_NOTE.replace("type: action\n", "type: action\ninputs:\n  - wrongname\n")
  p.write_text(drifted)

  code = main(["--check", str(tmp_path)])

  assert code == 1
  assert p.read_text() == drifted, "the gate must not fix what it is gating"
  # And it must STAY red — a second run reporting clean is the flaky-CI
  # signature this bug produced.
  assert main(["--check", str(tmp_path)]) == 1


def test_main_without_check_still_stamps(tmp_path: Path):
  """Regression guard — the write path is the pass's whole job."""
  p = tmp_path / "stale.md"
  p.write_text(_INPUT_NOTE.replace("type: action\n", "type: action\ninputs:\n  - wrongname\n"))

  assert main([str(tmp_path)]) == 0

  out = p.read_text()
  assert "wrongname" not in out
  for name in _expected_names(_INPUT_NOTE):
    assert name in out


def test_main_check_on_a_clean_vault_exits_0(tmp_path: Path):
  p = tmp_path / "ok.md"
  p.write_text(_INPUT_NOTE)
  main([str(tmp_path)])

  assert main(["--check", str(tmp_path)]) == 0
