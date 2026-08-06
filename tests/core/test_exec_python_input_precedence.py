"""Drain 2026-08-06-1230 issue (d) — inputs must shadow injected globals.

The canonical-form contract (stated at exec_python's local_ns build:
"input precedence per the canonical-form composition design") is that a
cohort's declared input always wins a name collision. Pre-fix, the
`**_domain_globals_for(domains)` spread came AFTER `**inputs`, so the
75 injected bundle names (music21 submodules, moda/music lib chips,
`tick_range`, ...) silently overrode same-named inputs. Founding
instance: chord_builder_smoke.md declares `inputs: [chord]`; its
`Return chord.` compute returned the music21.chord MODULE — which the
plugin's output panel cannot render, so the driver saw nothing at all.
"""

from forge.core.executor import exec_python

CODE = """
def compute(context):
  return {name}
"""


def _run(input_name, value):
  stdout, result = exec_python(
    CODE.format(name=input_name), {input_name: value}, snippet_id="t",
  )
  return result


def test_input_named_chord_shadows_music21_bundle_module():
  # The chord_builder_smoke case verbatim: a widget serializes pitches
  # into an input named `chord`; compute must see THAT list, not
  # music21.chord.
  assert _run("chord", ["C3", "E3", "G3"]) == ["C3", "E3", "G3"]


def test_input_named_note_shadows_music21_bundle_module():
  assert _run("note", "C4") == "C4"


def test_input_named_tick_range_shadows_moda_lib_chip():
  # Same rule, moda-lib name class (L11 cross-domain coverage).
  assert _run("tick_range", 7) == 7


def test_input_named_random_shadows_base_injected_module():
  # Base names (random/math/numpy) are injected too; the input still
  # wins. The user asked for a value called `random`; giving them the
  # stdlib module instead is the same silent-shadow failure mode.
  assert _run("random", 42) == 42


def test_non_colliding_input_unchanged():
  assert _run("pitches", ["E2", "C3"]) == ["E2", "C3"]


def test_bundle_names_still_injected_when_not_shadowed():
  # No-op stays no-op: with NO colliding input declared, the injected
  # names must still be present — a snippet that genuinely uses the
  # music21 `chord` module keeps working.
  stdout, result = exec_python(
    "def compute(context):\n  return chord.__name__\n",
    {"pitches": ["E2"]}, snippet_id="t",
  )
  assert result == "music21.chord"
