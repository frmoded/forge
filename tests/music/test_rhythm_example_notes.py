"""Beat-as-data Phases 2+3 (drain 2026-10-04-2330): the rhythm_data example notes execute end to end through the
real engine (SnippetRegistry -> GraphResolver -> exec_python), from the music-theory SOURCE vault.

Skipped when the sibling vault checkout is absent (same convention as the other vault-reading tests)."""
import os
import re

import pytest
import yaml

from forge.core.executor import exec_python, resolve_action_code
from forge.core.registry import GraphResolver, SnippetRegistry
from forge.core.sync_state import derive_sync_state

_VAULT = os.path.expanduser("~/projects/music-theory")
_RHYTHM_DIR = os.path.join(_VAULT, "rhythm_data")

pytestmark = pytest.mark.skipif(
  not os.path.isfile(os.path.join(_RHYTHM_DIR, "rhythm_multiplex.md")),
  reason="music-theory vault (rhythm_data) not found",
)


@pytest.fixture(scope="module")
def world():
  reg = SnippetRegistry()
  reg.scan(_VAULT)
  return GraphResolver(reg), reg


def _run_note(world, snippet_id):
  res, reg = world
  snip = res.resolve(snippet_id)
  _, result = exec_python(
    resolve_action_code(snip), {}, res,
    vault_path=_VAULT, registry=reg, snippet_id=snip["snippet_id"], domains=["music"],
  )
  return result


def _names(score):
  return [p.getInstrument().instrumentName for p in score.parts]


def _vels(part):
  return [n.volume.velocity for n in part.flatten().notes]


def test_rhythm_sequence_is_two_bars_with_same_instrument_staves_merged(world):
  score = _run_note(world, "rhythm_sequence")
  assert _names(score) == ["Kick", "Snare", "Closed Hi-Hat"]
  assert [len(p.getElementsByClass("Measure")) for p in score.parts] == [2, 2, 2]
  kick = [float(n.offset) for n in score.parts[0].flatten().notes]
  # straight rock first (kick on steps 0 and 8 -> 0.0, 2.0), then syncopated (0, 3, 10 -> 4.0, 4.75, 6.5)
  assert kick == [0.0, 2.0, 4.0, 4.75, 6.5]


def test_rhythm_accented_is_one_bar_with_the_hand_worked_velocities(world):
  score = _run_note(world, "rhythm_accented")
  assert _names(score) == ["Kick", "Snare", "Closed Hi-Hat"]
  assert [len(p.getElementsByClass("Measure")) for p in score.parts] == [1, 1, 1]
  assert [_vels(p) for p in score.parts] == [
    [112, 72],
    [72, 112],
    [112, 112, 72, 112, 72, 112, 112, 112],
  ]
  # Beatbox Phase 3b: the loud hits carry a visible Accent mark — kick 1, snare 1, hi-hat 6.
  assert [sum(any(type(a).__name__ == "Accent" for a in n.articulations) for n in p.flatten().notes)
          for p in score.parts] == [1, 1, 6]


def test_shipped_rhythm_multiplex_output_is_unchanged_six_parts_no_velocities_set(world):
  """Prompt §8: the shipped multiplex must produce identical output after the schema extension."""
  score = _run_note(world, "rhythm_multiplex")
  assert _names(score) == ["Kick", "Snare", "Closed Hi-Hat"] * 2
  assert [len(p.getElementsByClass("Measure")) for p in score.parts] == [1] * 6
  assert all(set(_vels(p)) == {None} for p in score.parts)
  assert all(not n.articulations for p in score.parts for n in p.flatten().notes)   # no accent marks on boolean data


@pytest.mark.parametrize("name", ["rhythm_sequence", "rhythm_accented"])
def test_new_example_notes_derive_as_synced_from_their_hash_lineage(name):
  text = open(os.path.join(_RHYTHM_DIR, name + ".md"), encoding="utf-8").read()
  fm = yaml.safe_load(re.match(r"---\n(.*?)\n---", text, re.S).group(1))
  assert derive_sync_state(fm) == "synced"
