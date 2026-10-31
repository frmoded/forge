"""2026-10-31-1100 (score-first M17b, design 4.14): compose_sections - the SECTIONS of a composition: bars played one section after another.

A section is {"bars": [<rhythm-data bars>], "length": N or None, "source": <the name of the note the bars came from, optional>}. The rules (driver, 2026-10-30):
  * a section whose `length` is more than its bars is REPEATED (the whole run of its bars, again from the first bar) until it has `length` bars, and one whose `length` is less is CUT to it:
    a section is never padded with rests and never stretched; `length` None (or absent) is "all the bars it has", once;
  * the sections are then CONCATENATED in order;
  * every bar keeps its OWN tempo: nothing is re-timed across sections (that is what an arrangement does);
  * sections that disagree on time_signature, steps or group_size are a plain refusal naming both sections, the field and both values (v1: one meter per piece);
  * pure: the inputs are never changed and the result shares no list with them; no randomness; no hit is added or lost; velocities are kept.
compose_sections_lineage says, per bar of the result, {"section": its number from 1, "source": the section's note name or None, "bar": the number (from 1) of the section's own bar it plays, "tempo_bpm": its tempo}.

Hand-worked pin (16 steps, group 4): section 1 is `a` (2 bars: kick [0], kick [4]) for 5 bars, section 2 is `b` (1 bar: snare [4]) with no length, section 3 is `c` (3 bars) for 2 bars.
  section 1 -> a1 a2 a1 a2 a1 (repeated to fill 5);  section 2 -> b1 (all of it, once);  section 3 -> c1 c2 (cut to 2);  the result has 8 bars.
"""
import copy
import random

import pytest

from forge.music import lib


def _bar(tempo=100, swing=0, steps=16, group=4, ts="4/4", **channels):
  out = {"time_signature": ts, "steps": steps, "group_size": group, "swing_pct": swing, "tempo_bpm": tempo, "channels": {}}
  for name, at in channels.items():
    if isinstance(at, (set, list, tuple)):
      at = {i: True for i in at}
    out["channels"][name] = [at.get(i, False) for i in range(steps)]
  return out


def _hits(bar, channel):
  return [i for i, v in enumerate(bar["channels"][channel]) if v is not False and v != 0]


def _section(bars, length=None, source=None):
  out = {"bars": bars}
  if length is not None:
    out["length"] = length
  if source is not None:
    out["source"] = source
  return out


A = [_bar(120, kick={0}), _bar(120, kick={4})]
B = [_bar(90, snare={4})]
C = [_bar(100, hihat={0}), _bar(100, hihat={2}), _bar(100, hihat={6})]


# ---- the hand-worked pin ---------------------------------------------------------------------------------------------------------------------------------------------------------

def test_hand_worked_repeat_to_fill_whole_once_and_cut():
  out = lib.compose_sections([_section(A, 5, "a"), _section(B, None, "b"), _section(C, 2, "c")])
  assert len(out) == 8
  assert [_hits(b, "kick") for b in out[:5]] == [[0], [4], [0], [4], [0]]
  assert _hits(out[5], "snare") == [4]
  assert [_hits(b, "hihat") for b in out[6:]] == [[0], [2]]
  assert [b["tempo_bpm"] for b in out] == [120] * 5 + [90] + [100] * 2


def test_a_length_equal_to_the_bars_is_the_bars_once():
  out = lib.compose_sections([_section(A, 2)])
  assert out == A


def test_a_length_absent_and_a_length_none_are_the_same_as_all_the_bars():
  assert lib.compose_sections([{"bars": A}]) == lib.compose_sections([{"bars": A, "length": None}]) == A


def test_a_section_is_never_padded_or_stretched():
  out = lib.compose_sections([_section(B, 1), _section(B, 3)])
  assert len(out) == 4 and all(_hits(b, "snare") == [4] for b in out)
  assert all("kick" not in b["channels"] for b in out)           # no rest bar, no channel invented


def test_every_bar_keeps_its_own_tempo_across_sections():
  slow = [_bar(60, kick={0})]
  fast = [_bar(180, kick={0})]
  assert [b["tempo_bpm"] for b in lib.compose_sections([_section(slow, 2), _section(fast, 2)])] == [60, 60, 180, 180]


def test_sections_may_have_different_channels():
  out = lib.compose_sections([_section(A, 1), _section(B, 1)])
  assert set(out[0]["channels"]) == {"kick"} and set(out[1]["channels"]) == {"snare"}
  lib.rhythm_bars_to_stream(out)                                  # the Score still draws (the writer pads the channels)


# ---- refusals ----------------------------------------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [("time_signature", "3/4"), ("steps", 12), ("group_size", 3)])
def test_a_different_meter_steps_or_group_is_a_plain_refusal_naming_both_sections(field, value):
  odd = _bar(100, kick={0})
  odd[field] = value
  if field == "steps":
    odd["channels"] = {"kick": [True] + [False] * 11}
  with pytest.raises(ValueError) as e:
    lib.compose_sections([_section(A, 2, "a"), _section(B, 1, "b"), _section([odd], 1, "c")])
  m = str(e.value)
  assert m.startswith("compose_sections:")
  assert "section 3" in m and "section 1" in m and field in m and repr(value) in m


def test_a_bar_inside_one_section_that_differs_names_its_number():
  odd = _bar(100, kick={0})
  odd["time_signature"] = "3/4"
  with pytest.raises(ValueError, match=r"compose_sections: section 2 bar 2 has time_signature '3/4' but section 1 has '4/4'"):
    lib.compose_sections([_section(A, 2), _section([_bar(100, kick={0}), odd], 2)])


def test_a_bar_inside_the_first_section_that_differs_names_the_first_bar_of_that_section():
  odd = _bar(100, kick={0})
  odd["steps"] = 12
  odd["channels"] = {"kick": [True] + [False] * 11}
  with pytest.raises(ValueError, match=r"compose_sections: section 1 bar 2 has steps 12 but section 1 bar 1 has 16"):
    lib.compose_sections([_section([_bar(100, kick={0}), odd], 2)])


@pytest.mark.parametrize("bad", [None, [], "x", 3, {"bars": A}, [None], [{}], [{"bars": []}], [{"bars": "x"}], [{"bars": [3]}]])
def test_malformed_sections_are_refused_in_a_sentence_that_names_the_function(bad):
  with pytest.raises(ValueError, match="compose_sections"):
    lib.compose_sections(bad)


@pytest.mark.parametrize("length", [0, -1, 1.5, True, "4", [4]])
def test_a_length_that_is_not_a_whole_number_of_bars_from_one_is_refused(length):
  with pytest.raises(ValueError, match=r"compose_sections: section 1 length must be a whole number of bars, 1 or more"):
    lib.compose_sections([{"bars": A, "length": length}])


def test_a_source_that_is_not_a_name_is_refused():
  with pytest.raises(ValueError, match="compose_sections: section 1 source"):
    lib.compose_sections([{"bars": A, "source": ""}])


def test_a_bar_that_the_engine_would_not_draw_is_refused_like_every_other_rhythm_function():
  bad = _bar(100, kick={0})
  bad["channels"]["marimba"] = [False] * 16
  with pytest.raises(ValueError, match="compose_sections: .*unknown channel"):
    lib.compose_sections([_section([bad], 1)])


# ---- purity and properties ----------------------------------------------------------------------------------------------------------------------------------------------

def test_the_inputs_are_not_changed_and_the_result_shares_nothing_with_them():
  sections = [_section(A, 5, "a"), _section(C, 2, "c")]
  before = copy.deepcopy(sections)
  out = lib.compose_sections(sections)
  assert sections == before
  out[0]["channels"]["kick"][0] = False
  out[2]["tempo_bpm"] = 1
  assert sections == before and out[4]["channels"]["kick"][0] is True     # a repeated bar is its own copy


def _random_bar(rng, tempo):
  steps = 16
  chans = {}
  for name in rng.sample(["kick", "snare", "hihat", "bell", "claves"], rng.randint(1, 3)):
    chans[name] = [rng.choice([False, False, True, 40, 100]) for _ in range(steps)]
  return {"time_signature": "4/4", "steps": steps, "group_size": 4, "swing_pct": 0, "tempo_bpm": tempo, "channels": chans}


@pytest.mark.parametrize("seed", range(40))
def test_properties_hold_on_random_sections(seed):
  rng = random.Random(seed)
  sections = []
  for s in range(rng.randint(1, 6)):
    bars = [_random_bar(rng, rng.choice([60, 90, 120, 150])) for _ in range(rng.randint(1, 5))]
    sections.append(_section(bars, rng.choice([None, rng.randint(1, 9)]), f"note_{s}"))
  before = copy.deepcopy(sections)
  out = lib.compose_sections(sections)
  lineage = lib.compose_sections_lineage(sections)
  assert sections == before
  assert len(out) == sum(len(s["bars"]) if "length" not in s else s["length"] for s in sections) == len(lineage)
  for position, (bar, line) in enumerate(zip(out, lineage)):
    section = sections[line["section"] - 1]
    assert line["source"] == section["source"]
    assert bar == section["bars"][line["bar"] - 1]                 # the bar played IS the section's own bar, whole
    assert line["tempo_bpm"] == bar["tempo_bpm"]
    assert set(line) == {"section", "source", "bar", "tempo_bpm"}
  seen = 0
  for number, section in enumerate(sections, start=1):          # sections come out in order, each a cycle of its own bars
    n = section["length"] if "length" in section else len(section["bars"])
    run = [line for line in lineage if line["section"] == number]
    assert len(run) == n and lineage[seen:seen + n] == run
    assert [line["bar"] for line in run] == [(i % len(section["bars"])) + 1 for i in range(n)]
    seen += n


def test_the_result_feeds_rhythm_bars_to_stream():
  out = lib.compose_sections([_section(A, 3), _section(B, 2)])
  assert lib.rhythm_bars_to_stream(out) is not None


# ---- lineage -----------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_lineage_hand_worked():
  got = lib.compose_sections_lineage([_section(A, 5, "a"), _section(B, None, "b"), _section(C, 2)])
  assert got[:6] == [
    {"section": 1, "source": "a", "bar": 1, "tempo_bpm": 120}, {"section": 1, "source": "a", "bar": 2, "tempo_bpm": 120},
    {"section": 1, "source": "a", "bar": 1, "tempo_bpm": 120}, {"section": 1, "source": "a", "bar": 2, "tempo_bpm": 120},
    {"section": 1, "source": "a", "bar": 1, "tempo_bpm": 120}, {"section": 2, "source": "b", "bar": 1, "tempo_bpm": 90},
  ]
  assert got[6:] == [{"section": 3, "source": None, "bar": 1, "tempo_bpm": 100}, {"section": 3, "source": None, "bar": 2, "tempo_bpm": 100}]


def test_lineage_checks_the_sections_exactly_as_compose_sections_does():
  odd = _bar(100, kick={0})
  odd["steps"] = 8
  odd["channels"] = {"kick": [True] + [False] * 7}
  with pytest.raises(ValueError, match="compose_sections_lineage: section 2"):
    lib.compose_sections_lineage([_section(A, 1), _section([odd], 1)])
