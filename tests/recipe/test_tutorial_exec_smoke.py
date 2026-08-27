"""Exec-level smoke for forge-tutorial V2 migrations.

Per drain v0.2.167 §4 each tutorial note was transpile-smoked via
resolve_action_code. That caught parser/transpile bugs but NOT runtime
gaps — e.g., the read_data_snippet `body_format` vs `content_type`
regression (caught only when driver Forge-clicked show_colors at
runtime).

This module exec-smokes each migrated note end-to-end against the
forge-tutorial vault (resolves siblings via the same shim mechanism
the plugin uses). Captures stdout to assert output content where the
note prints something the driver expects to see.
"""

import io
import os
import sys

import pytest

from forge.core.executor import (
    exec_python,
    resolve_action_code,
)
from forge.core.registry import GraphResolver, SnippetRegistry
from forge.recipe.parser import ParseError

from tests.music._helpers import _find_vault as _find_music_vault


def collect_action_note_basenames(vault):
  """Basenames of every `type: action` note that BELONGS to `vault`.

  Dot-directories are pruned from the walk. Drain 2026-08-17-1210: the
  driver installs the plugin into the standalone forge-tutorial vault,
  so `.obsidian/plugins/forge-client-obsidian/assets/vaults/` holds the
  plugin's own bundled copies of the OTHER vaults (music-theory,
  forge-moda, music-core). A raw `os.walk` collected those too, and the
  coverage guard then demanded exec-smoke tests for notes that do not
  exist in forge-tutorial at all — `murmuration`, `companions`,
  `create_ink_particles`. The duplicate entries in its own failure
  message (`describe_it` twice, `mood` twice) were the same basename
  found once in the vault and once in the bundle.

  `.forge/` (edge snapshots) is pruned by the same rule, which is also
  correct: a frozen edge is not an authored note.

  Pruning is done by mutating `dirs` in place — the documented way to
  stop `os.walk` from descending, and the reason this loop binds `dirs`
  rather than discarding it.
  """
  found = []
  for root, dirs, files in os.walk(vault):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for fn in files:
      if not fn.endswith(".md"):
        continue
      path = os.path.join(root, fn)
      try:
        with open(path) as f:
          head = f.read(200)
      except OSError:
        continue
      # YAML frontmatter `type: action` check — same way the
      # registry classifies notes.
      if "\ntype: action" in head or head.startswith("---\ntype: action"):
        found.append(fn[:-len(".md")])
  return found


def _find_tutorial_vault():
  """Mirrors _find_music_vault but for forge-tutorial."""
  import os
  candidates = [
    os.environ.get("FORGE_TUTORIAL_VAULT_PATH"),
    os.path.expanduser("~/projects/forge-tutorial"),
  ]
  for c in candidates:
    if c and os.path.isdir(c):
      return c
  return None


@pytest.fixture(scope="module")
def tutorial_resolver():
  vault = _find_tutorial_vault()
  if vault is None:
    pytest.skip("forge-tutorial vault not found")
  reg = SnippetRegistry()
  reg.scan(vault)
  return GraphResolver(reg), reg, vault


def _run(tutorial_resolver, snippet_id, **inputs):
  res, reg, vault = tutorial_resolver
  snip = res.resolve(snippet_id)
  code = resolve_action_code(snip)
  stdout, result = exec_python(
      code, inputs, res,
      vault_path=vault, registry=reg,
      snippet_id=snip["snippet_id"],
  )
  return stdout, result


class TestActionNotesExec:
  def test_hello_world(self, tutorial_resolver):
    # CW-tutorial-01-hello-recipe-print-shift (drain 2026-07-23-1305):
    # hello_world's Recipe was rewritten from `[[print]] "hello, world".`
    # to `Return "hello, world".` to eliminate the phantom `[[print]]`
    # few-shot bleed vector to the LLM. Post-shift the value renders in
    # the Forge panel via the returned value (same user-visible
    # outcome), not stdout — the test assertion follows.
    _, result = _run(tutorial_resolver, "hello_world")
    assert result == "hello, world"

  def test_greeting(self, tutorial_resolver):
    # CW-tutorial-full-return-sweep (drain 2026-07-23-1500):
    # greeting.md's Recipe shifted from `[[print]] greeting.` to
    # `Return greeting.` — output surface flipped from stdout to
    # return value. Assertion follows.
    _, result = _run(tutorial_resolver, "greeting")
    assert result == "Hello, Ada"

  def test_excited_returns_word_with_exclam(self, tutorial_resolver):
    _, result = _run(tutorial_resolver, "excited", word="yay")
    assert result == "yay!"

  def test_cheer(self, tutorial_resolver):
    # CW-tutorial-full-return-sweep (drain 2026-07-23-1500):
    # cheer.md now Returns instead of printing — assertion shifted.
    _, result = _run(tutorial_resolver, "cheer")
    assert result == "hooray!"

  def test_fix_the_call(self, tutorial_resolver):
    """Chapter 3's broken-on-purpose note (drain 2026-08-27-1200).

    It demonstrates the missing-`word=` mistake, so the guard is that it
    FAILS -- and fails at the E-- parse layer, not at runtime. Asserting the
    exact error class matters: if a future parser change made the positional
    call legal, the note would quietly start working and the exercise would
    be gone with nothing going red.
    """
    res, reg, vault = tutorial_resolver
    snip = res.resolve("fix_the_call")
    with pytest.raises(ParseError) as exc:
      resolve_action_code(snip)
    assert "malformed kwarg" in str(exc.value)

  def test_excited_word_returns_word(self, tutorial_resolver):
    _, result = _run(tutorial_resolver, "excited_word")
    assert result == "wonderful"

  def test_weather_pleasant_at_72(self, tutorial_resolver):
    # CW-tutorial-full-return-sweep (drain 2026-07-23-1500):
    # weather.md's If/Otherwise branches both Return now — the
    # chosen branch hands its string back as the note's result.
    _, result = _run(tutorial_resolver, "weather")
    assert result == "It's pleasant."

  def test_countdown(self, tutorial_resolver):
    stdout, _ = _run(tutorial_resolver, "countdown")
    # Order matters — 3, 2, 1, then Liftoff!.
    idx_3 = stdout.find("3")
    idx_2 = stdout.find("2")
    idx_1 = stdout.find("1")
    idx_lift = stdout.find("Liftoff!")
    assert -1 < idx_3 < idx_2 < idx_1 < idx_lift, (
      f"countdown order broken; stdout={stdout!r}"
    )

  def test_show_colors_reads_data_note(self, tutorial_resolver):
    """Regression guard: this is the bug the driver hit on v0.2.168 —
    show_colors calls [[colors]] which is a data note. read_data_snippet
    must accept V2's `body_format:` not just V1's `content_type:`.
    """
    stdout, _ = _run(tutorial_resolver, "show_colors")
    assert "red" in stdout
    assert "green" in stdout
    assert "blue" in stdout

  def test_factorial_5(self, tutorial_resolver):
    _, result = _run(tutorial_resolver, "factorial", n=5)
    assert result == 120

  def test_factorial_1(self, tutorial_resolver):
    _, result = _run(tutorial_resolver, "factorial", n=1)
    assert result == 1

  def test_show_factorial(self, tutorial_resolver):
    # CW-tutorial-full-return-sweep (drain 2026-07-23-1500):
    # show_factorial.md now Returns instead of printing.
    _, result = _run(tutorial_resolver, "show_factorial")
    assert result == 120

  def test_octopus_fact(self, tutorial_resolver):
    """octopus_fact uses `{{...}}` slot syntax. Pre-V2.1 (drain at
    2026-06-28-2130) we asserted the resolved string was in stdout;
    post-restore the resolution is LLM-driven (or cached in
    frontmatter), so this exec-smoke test now just confirms that the
    `{{...}}` slot triggers SlotCacheMissError (the expected first-
    pass behavior). A full resolved-cache E2E lives in
    `tests/core/test_v2_slot_resolution.py`.

    RESTORED at drain 2026-08-25-0130, and the round trip is the
    lesson. Drain 0110 rewrote this assertion after it started failing,
    on the reasoning that the note declares `source_facet: python` with
    a cached `# Python`, so honouring the declared facet was correct
    and Chapter 9 had stopped demonstrating slots. That reasoning was
    sound; the premise was not.

    `source_facet: python` was never in the note. It was an UNCOMMITTED
    edit in the driver's `~/projects/forge-tutorial` working tree —
    which is exactly what `_find_tutorial_vault` binds to. HEAD, and
    the copy the plugin bundles and ships, both carry
    `source_facet: description` with `return None`. Chapter 9 works.

    THE HAZARD, stated plainly because it will recur: this module reads
    a LIVE WORKING TREE, not a fixture. A failure here can be caused by
    uncommitted state, and "the assertion encodes a stale assumption"
    is an explanation that fits that evidence just as well as the true
    one. Before rewriting an assertion in this file, diff the vault
    (`git -C ~/projects/forge-tutorial status`) and confirm the note
    you are reasoning about is the note that ships."""
    from forge.core.slot_cache import SlotCacheMissError
    import pytest
    with pytest.raises(SlotCacheMissError) as exc_info:
      _run(tutorial_resolver, "octopus_fact")
    assert any(
      "octopus" in m["slot_text"].lower()
      for m in exc_info.value.missing
    )

  # -- drain 2026-08-19-0910: the three notes the coverage guard named --
  #
  # These are the notes the Input-keyword arc made interesting, and until
  # now their only sentinel was a human running the dropdown smoke. Each
  # assertion below is the headless twin of a UI behaviour.

  def test_describe_it(self, tutorial_resolver):
    """Cross-note composition: describe_it Calls [[excited_word]] and
    splices its return into a sentence. Pins the composition, and with
    it the sibling-resolution path describe_it depends on."""
    _, result = _run(tutorial_resolver, "describe_it")
    assert result == "This is wonderful."

  def test_function_inputs_uses_declared_defaults(self, tutorial_resolver):
    """Both Inputs are declared with defaults; calling with no kwargs
    must use them rather than raising for missing arguments."""
    _, result = _run(tutorial_resolver, "function_inputs")
    assert result == "Ada Lovelace"

  def test_function_inputs_supplied_values_win(self, tutorial_resolver):
    """The defaulted-vs-supplied path: passing kwargs overrides the
    declared defaults. Without this, a regression that ignored caller
    input would still pass the defaults test."""
    _, result = _run(
      tutorial_resolver, "function_inputs",
      first_name="Grace", last_name="Hopper",
    )
    assert result == "Grace Hopper"

  def test_mood_cheerful_is_the_declared_default(self, tutorial_resolver):
    """`Input style: 'cheerful' | 'formal' | 'sleepy' = "cheerful"` — the
    enum-literal Input that renders as the Run dialog's dropdown. No
    kwargs means the declared default literal."""
    _, result = _run(tutorial_resolver, "mood")
    assert result == "Hey hey hey!!!"

  def test_mood_output_varies_with_each_enum_literal(self, tutorial_resolver):
    """The headless twin of the dropdown smoke: every literal the Input
    declares selects a distinct branch. Asserting distinctness as well as
    values catches a regression that collapsed the If-chain to one arm
    while still returning something."""
    outputs = {}
    for literal in ("cheerful", "formal", "sleepy"):
      _, result = _run(tutorial_resolver, "mood", style=literal)
      outputs[literal] = result
    assert outputs["cheerful"] == "Hey hey hey!!!"
    assert outputs["formal"] == "Good day to you."
    assert outputs["sleepy"] == "...zzz..."
    assert len(set(outputs.values())) == 3, (
      f"each declared literal must select its own branch; got {outputs}"
    )

class TestAllTutorialActionNotesHaveCoverage:
  """Coverage-guard: every `type: action` note in the tutorial vault
  must have a corresponding `test_<basename>` method in
  TestActionNotesExec. Pre-v0.2.200 the driver hit a forge-bluh smoke
  failure on `hello_world` after generate produced
  `Call [[print]] with text="..."` — but the canonical hello_world.md
  uses the shorthand form so existing tests passed. This guard means
  ANY new action note added to the vault gets pinned to an exec-smoke
  immediately."""

  def test_every_action_note_has_a_test(self, tutorial_resolver):
    _, _, vault = tutorial_resolver
    action_notes = collect_action_note_basenames(vault)
    test_methods = {
      m for m in dir(TestActionNotesExec) if m.startswith("test_")
    }
    missing = []
    for basename in sorted(action_notes):
      # Convention: test name contains the basename. Some tests have
      # extra suffix (e.g. test_excited_returns_word_with_exclam).
      if not any(basename in m for m in test_methods):
        missing.append(basename)
    assert not missing, (
      f"Action notes missing exec-smoke coverage in "
      f"TestActionNotesExec: {missing}. Add a test_<basename> method "
      f"that runs the note and asserts on its observable output."
    )


class TestPrintShorthandVsKwargForm:
  """v0.2.200 — lock the transpiler's handling of the two ways the LLM
  might encode a print call. Pre-fix, the V2 prompt's Example 1 taught
  `Call [[print]] with text="..."`; the LLM faithfully reproduced it,
  the transpiler rendered `print(text="...")`, and the snippet crashed
  at runtime with TypeError. The fix is upstream (prompt + service
  catalog) but THIS test pins both the broken mapping (so a regression
  surfaces as a documented expectation rather than a mystery) and the
  working shorthand mapping."""

  def test_shorthand_form_transpiles_to_positional_print(self):
    from forge.recipe import parse, transpile
    code = transpile(parse('[[print]] "hello, world".\nReturn.\n'))
    # The shorthand-call statement becomes `print("hello, world")`.
    assert 'print(\'hello, world\')' in code or 'print("hello, world")' in code
    assert 'text=' not in code

  def test_kwarg_form_transpiles_to_text_kwarg_which_would_crash_at_runtime(self):
    """If the LLM regresses to `Call [[print]] with text=...`, this is
    what the transpiler emits — Python's builtin `print` does NOT have
    a `text` kwarg, so executing the result would raise
    `TypeError: print() got an unexpected keyword argument 'text'`.
    Test name documents the failure mode so future debuggers find this
    fast.
    """
    from forge.recipe import parse, transpile
    code = transpile(parse('Call [[print]] with text="hi".\nReturn.\n'))
    # Verbatim kwarg passthrough — broken, but documented.
    assert "print(text='hi')" in code or 'print(text="hi")' in code

  def test_shorthand_form_executes_print_at_runtime(self):
    """End-to-end positive: the shorthand form actually runs and
    prints. Mirrors what an LLM-generated hello_world Recipe SHOULD
    do post-v0.2.200."""
    import io
    import sys
    from forge.recipe import parse, transpile
    from forge.core.executor import exec_python
    code = transpile(parse('[[print]] "hello, world".\nReturn.\n'))
    stdout, _ = exec_python(
      code, inputs={}, snippet_id="hello_world_synthetic",
    )
    assert "hello, world" in stdout

  def test_kwarg_form_raises_typeerror_at_runtime(self):
    """End-to-end negative: confirm the broken kwarg form actually
    crashes with the documented TypeError. This is the user-visible
    error that triggered the v0.2.200 bug report."""
    import pytest
    from forge.recipe import parse, transpile
    from forge.core.executor import exec_python, SnippetExecError
    code = transpile(parse('Call [[print]] with text="hi".\nReturn.\n'))
    with pytest.raises(SnippetExecError) as exc_info:
      exec_python(
        code, inputs={}, snippet_id="hello_world_synthetic_broken",
      )
    assert "text" in str(exc_info.value)
    assert "keyword argument" in str(exc_info.value)


class TestActionNoteWalkFilter:
  """Drain 2026-08-17-1210 — the dot-directory filter, proved on a
  fixture tree rather than on the live vault.

  Non-vacuity matters here more than usual: a filter that excluded
  EVERYTHING would make the coverage guard pass for the wrong reason
  and silence the real gap it exists to surface. Each test below
  asserts both halves — the decoy is gone AND the real note survived.
  """

  ACTION_NOTE = "---\ntype: action\n---\n\n# Description\n\nDo a thing.\n"

  def _tree(self, root):
    """A vault with one real note and one decoy buried in a dot-dir,
    mirroring the live layout: the installed plugin ships another
    vault's notes under `.obsidian/plugins/.../assets/vaults/`."""
    real = root / "01-hello" / "hello_world.md"
    real.parent.mkdir(parents=True)
    real.write_text(self.ACTION_NOTE)

    decoy = (root / ".obsidian" / "plugins" / "forge-client-obsidian"
             / "assets" / "vaults" / "music-theory" / "percussion"
             / "murmuration.md")
    decoy.parent.mkdir(parents=True)
    decoy.write_text(self.ACTION_NOTE)

    snapshot = root / ".forge" / "edges" / "authoring" / "frozen.md"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(self.ACTION_NOTE)
    return real, decoy, snapshot

  def test_notes_inside_dot_directories_are_excluded(self, tmp_path):
    real, decoy, snapshot = self._tree(tmp_path)
    # The fixture is real: if these ever stop existing the test below
    # would pass vacuously.
    assert decoy.exists() and snapshot.exists() and real.exists()

    found = collect_action_note_basenames(str(tmp_path))

    assert "murmuration" not in found, (
      "a note from the installed plugin's bundled copy of ANOTHER vault "
      "was collected as if it belonged to this one"
    )
    assert "frozen" not in found, "a .forge/ edge snapshot is not an authored note"

  def test_the_filter_still_collects_real_notes(self, tmp_path):
    self._tree(tmp_path)
    found = collect_action_note_basenames(str(tmp_path))
    assert found == ["hello_world"], (
      f"the filter must exclude only dot-directories; got {found}"
    )

  def test_a_vault_of_only_dot_directories_yields_nothing(self, tmp_path):
    decoy = tmp_path / ".obsidian" / "buried.md"
    decoy.parent.mkdir(parents=True)
    decoy.write_text(self.ACTION_NOTE)
    assert collect_action_note_basenames(str(tmp_path)) == []

  def test_non_action_notes_are_still_ignored(self, tmp_path):
    (tmp_path / "data.md").write_text("---\ntype: data\n---\n\nrows: 3\n")
    (tmp_path / "act.md").write_text(self.ACTION_NOTE)
    assert collect_action_note_basenames(str(tmp_path)) == ["act"]
