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
    stdout, _ = _run(tutorial_resolver, "octopus_fact")
    assert "three hearts" in stdout
