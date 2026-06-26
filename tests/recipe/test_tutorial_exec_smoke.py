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
import sys

import pytest

from forge.core.executor import (
    exec_python,
    resolve_action_code,
)
from forge.core.registry import GraphResolver, SnippetRegistry

from tests.music._helpers import _find_vault as _find_music_vault


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
    stdout, _ = _run(tutorial_resolver, "hello_world")
    assert "hello, world" in stdout

  def test_greeting(self, tutorial_resolver):
    stdout, _ = _run(tutorial_resolver, "greeting")
    assert "Hello, Ada" in stdout

  def test_excited_returns_word_with_exclam(self, tutorial_resolver):
    _, result = _run(tutorial_resolver, "excited", word="yay")
    assert result == "yay!"

  def test_cheer(self, tutorial_resolver):
    stdout, _ = _run(tutorial_resolver, "cheer")
    assert "hooray!" in stdout

  def test_excited_word_returns_word(self, tutorial_resolver):
    _, result = _run(tutorial_resolver, "excited_word")
    assert result == "wonderful"

  def test_describe_forge(self, tutorial_resolver):
    stdout, _ = _run(tutorial_resolver, "describe_forge")
    assert "Forge is wonderful" in stdout

  def test_weather_pleasant_at_72(self, tutorial_resolver):
    stdout, _ = _run(tutorial_resolver, "weather")
    assert "pleasant" in stdout
    assert "hot" not in stdout

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
    stdout, _ = _run(tutorial_resolver, "show_factorial")
    assert "120" in stdout

  def test_octopus_fact(self, tutorial_resolver):
    """octopus_fact uses `{{...}}` slot syntax. Pre-V2.1 (drain at
    2026-06-28-2130) we asserted the resolved string was in stdout;
    post-restore the resolution is LLM-driven (or cached in
    frontmatter), so this exec-smoke test now just confirms that the
    `{{...}}` slot triggers SlotCacheMissError (the expected first-
    pass behavior). A full resolved-cache E2E lives in
    `tests/core/test_v2_slot_resolution.py`."""
    from forge.core.slot_cache import SlotCacheMissError
    import pytest
    with pytest.raises(SlotCacheMissError) as exc_info:
      _run(tutorial_resolver, "octopus_fact")
    assert any(
      "octopus" in m["slot_text"].lower()
      for m in exc_info.value.missing
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
    import os
    _, _, vault = tutorial_resolver
    action_notes = []
    for root, _dirs, files in os.walk(vault):
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
          action_notes.append(fn[:-len(".md")])
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
