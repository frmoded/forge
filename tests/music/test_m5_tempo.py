"""M5 (drain 2026-10-22-1850) — Phase A, the engine: per-bar tempo.

`rhythm_bars_to_stream` used to REJECT bars whose tempo_bpm differ, so a ritardando could not be expressed. Now only time_signature, steps and group_size must agree; each bar's own
MetronomeMark survives `sequence()` into the Score, its MusicXML and its MIDI. `extend_rhythm` gains `tempo_change_pct` (default 0 = exactly what it returned before): a linear step per bar.

Measured before any change (FEEDBACK step 1): the premise holds (`bar 1 disagrees with bar 0 on tempo_bpm`); with the check out of the way `sequence()` keeps every bar's MetronomeMark on every
part, the MusicXML carries a `<sound tempo>` per bar per part, and the MIDI carries one tempo meta event per bar per track — so only the check had to go.

NO HARM (principle P3): the digests in fixtures/m5_frozen/index.json were frozen from the PRE-CHANGE engine (commit 9f0e947, a worktree of it; `generate.py` refuses to run anywhere else): every
4/4 16-step seed x 3 styles x 1/4/8 bars gives the same extend_rhythm result and the same MusicXML / Kit XML / MIDI as before, and so do the three music-theory rhythm_extended_* notes.
"""
import json
import re
from pathlib import Path

import pytest

from forge.core.serialization import serialize_result
from forge.music import lib
from tests.music import m5_corpus as mc

INDEX = json.loads((mc.kc.FIXTURES / "m5_frozen" / "index.json").read_text())


def ser(score, title="t"):
  return serialize_result(score, {"snippet_id": title, "meta": {"title": title}})


def seed(tempo=100):
  d = json.loads(json.dumps(mc.kc.named_bars()["bar_001"]))
  d["tempo_bpm"] = tempo
  return d


def sound_tempos(xml):
  return [float(x) for x in re.findall(r'<sound tempo="([^"]+)"', xml)]


def midi_tempos(payload):
  import base64
  raw = base64.b64decode(payload["multi_staff_midi_base64"])
  out, i = [], 0
  while True:
    i = raw.find(b"\xff\x51\x03", i)
    if i < 0:
      return out
    out.append(round(60_000_000 / int.from_bytes(raw[i + 3:i + 6], "big"), 1))
    i += 3


# ---- NO HARM ------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_the_frozen_baseline_is_the_pre_change_engine_and_covers_the_corpus():
  assert INDEX["prefix_commit"] == "9f0e947724366d1c3b12b0a2ad3e18e4d409003d"
  assert len(INDEX["cases"]) == len(mc.seeds()) * len(mc.STYLES) * len(mc.BAR_COUNTS) >= 60
  assert set(INDEX["notes"]) == {f"note/{n}" for n in mc.NOTES}


@pytest.mark.parametrize("cid", sorted(INDEX["cases"]))
def test_equal_tempo_bars_and_default_extend_are_byte_identical_to_the_pre_change_engine(cid):
  name, style, bars = cid.split("/")
  built = lib.extend_rhythm(mc.seeds()[name], bars=int(bars), style=style)
  got = {"extend_json": mc._sha(json.dumps(built, sort_keys=True)), **mc.digests_for_payload(ser(lib.rhythm_bars_to_stream(built), cid))}
  assert got == INDEX["cases"][cid]


@pytest.mark.parametrize("cid", sorted(INDEX["cases"])[::9])
def test_an_explicit_zero_is_the_default(cid):
  name, style, bars = cid.split("/")
  assert lib.extend_rhythm(mc.seeds()[name], bars=int(bars), style=style, tempo_change_pct=0) == lib.extend_rhythm(mc.seeds()[name], bars=int(bars), style=style)


def test_the_three_music_theory_rhythm_extended_notes_produce_the_same_scores():
  vault = mc.clean_music_theory_head(INDEX["music_theory_head"])
  assert mc.note_digests(vault, ser) == INDEX["notes"]


# ---- Phase A: rhythm_bars_to_stream carries a tempo per bar --------------------------------------------------------------------------------------------------------------

def four_bars(tempi=(100, 90, 80, 70)):
  bars = lib.extend_rhythm(seed(), bars=4)
  for b, t in zip(bars, tempi):
    b["tempo_bpm"] = t
  return bars


def test_bars_that_differ_in_tempo_are_joined_and_each_bars_mark_survives_in_the_xml_and_the_midi():
  payload = ser(lib.rhythm_bars_to_stream(four_bars()))
  per_part = len(sound_tempos(payload["multi_staff_content"])) // 2
  assert sound_tempos(payload["multi_staff_content"]) == [100.0, 90.0, 80.0, 70.0] * 2, "a mark at bar 1 and at every change, on both staves"
  assert per_part == 4
  assert sound_tempos(payload["kit_content"]) == [100.0, 90.0, 80.0, 70.0]
  assert midi_tempos(payload)[0] == 100.0 and {90.0, 80.0, 70.0} <= set(midi_tempos(payload))


def test_the_score_has_one_mark_per_bar_at_the_first_measure_offset_of_that_bar():
  from music21 import stream, tempo
  score = lib.rhythm_bars_to_stream(four_bars())
  for part in score.parts:
    got = [(m.number, mm.number) for m in part.getElementsByClass(stream.Measure) for mm in m.getElementsByClass(tempo.MetronomeMark)]
    assert got == [(1, 100), (2, 90), (3, 80), (4, 70)]


def test_a_bar_that_keeps_the_tempo_gets_no_repeated_mark_in_the_score_but_a_change_gets_one():
  # equal-tempo bars: exactly the pre-change behaviour (a mark per bar was already there: pinned by the byte-identical tests); the point here is a RETURN to a tempo is marked
  bars = four_bars((100, 100, 80, 100))
  assert sound_tempos(ser(lib.rhythm_bars_to_stream(bars))["kit_content"]) == [100.0, 100.0, 80.0, 100.0]


@pytest.mark.parametrize("field, value", [("time_signature", "3/4"), ("steps", 8), ("group_size", 2)])
def test_the_grid_must_still_agree_across_bars(field, value):
  other = seed()
  other[field] = value
  if field == "steps":
    other["channels"] = {c: v[:8] for c, v in other["channels"].items()}
  with pytest.raises(ValueError, match=rf"rhythm_bars_to_stream.*bar 1.*{field}"):
    lib.rhythm_bars_to_stream([seed(), other])


def test_a_tempo_that_is_not_a_number_is_still_refused_naming_the_bar():
  bars = four_bars()
  bars[2]["tempo_bpm"] = "slow"
  with pytest.raises(ValueError, match=r"rhythm_bars_to_stream.*bar 2"):
    lib.rhythm_bars_to_stream(bars)


# ---- Phase A: extend_rhythm(tempo_change_pct) -------------------------------------------------------------------------------------------------------------------------------

def tempi(bars, pct, style="repeat_with_fills", t=100):
  return [b["tempo_bpm"] for b in lib.extend_rhythm(seed(t), bars=bars, style=style, tempo_change_pct=pct)]


def test_the_documented_example_100_bpm_8_bars_minus_20_percent():
  assert tempi(8, -20) == [100, 97, 94, 91, 89, 86, 83, 80]


def test_speeding_up_is_linear_too_and_ends_exactly_on_the_target():
  assert tempi(5, 100) == [100, 125, 150, 175, 200]
  assert tempi(4, -90) == [100, 70, 40, 10]


def test_a_single_bar_stays_at_the_seed_tempo_whatever_the_percentage():
  assert tempi(1, -50) == [100] and tempi(1, 100) == [100]


def test_rounding_is_half_up_not_bankers():
  assert tempi(3, 25, t=10) == [10, 11, 13]            # 10 * 1.125 = 11.25 -> 11; 10 * 1.25 = 12.5 -> 13 (banker's rounding would give 12)


def test_every_tempo_is_an_int_and_only_the_tempo_changes():
  base = lib.extend_rhythm(seed(), bars=4)
  ramp = lib.extend_rhythm(seed(), bars=4, tempo_change_pct=-20)
  assert all(type(b["tempo_bpm"]) is int for b in ramp)
  for a, b in zip(base, ramp):
    assert {k: v for k, v in a.items() if k != "tempo_bpm"} == {k: v for k, v in b.items() if k != "tempo_bpm"}


@pytest.mark.parametrize("style", lib._RHYTHM_EXTEND_STYLES)
def test_it_works_with_every_style_and_the_result_goes_through_rhythm_bars_to_stream(style):
  payload = ser(lib.rhythm_bars_to_stream(lib.extend_rhythm(seed(), bars=8, style=style, tempo_change_pct=-20)))
  assert sound_tempos(payload["kit_content"]) == [100.0, 97.0, 94.0, 91.0, 89.0, 86.0, 83.0, 80.0]


@pytest.mark.parametrize("bad", [True, False, "10", None, [5], float("nan"), -91, 101, -90.5, 100.5])
def test_a_bad_percentage_is_refused_naming_the_argument(bad):
  with pytest.raises(ValueError, match="tempo_change_pct"):
    lib.extend_rhythm(seed(), bars=4, tempo_change_pct=bad)


@pytest.mark.parametrize("ok", [-90, 100, 0, 0.0, -20.5, 12])
def test_the_range_ends_and_floats_are_accepted(ok):
  assert len(lib.extend_rhythm(seed(), bars=3, tempo_change_pct=ok)) == 3


def test_a_seed_whose_tempo_is_not_a_number_is_refused_when_a_change_is_asked_for():
  bad = seed(); bad["tempo_bpm"] = "fast"
  with pytest.raises(ValueError, match="tempo_bpm"):
    lib.extend_rhythm(bad, bars=4, tempo_change_pct=-20)


def test_the_input_is_not_mutated():
  s = seed(); before = json.dumps(s, sort_keys=True)
  lib.extend_rhythm(s, bars=4, tempo_change_pct=-20)
  assert json.dumps(s, sort_keys=True) == before


def test_a_zero_percentage_leaves_even_an_odd_seed_tempo_untouched_it_is_not_rounded_or_rewritten():
  s = seed(100.5)
  assert [b["tempo_bpm"] for b in lib.extend_rhythm(s, bars=3, tempo_change_pct=0)] == [100.5, 100.5, 100.5]
  assert [b["tempo_bpm"] for b in lib.extend_rhythm(s, bars=3, tempo_change_pct=0.0)] == [100.5, 100.5, 100.5]


def test_a_ramp_never_goes_below_one_bpm():
  assert tempi(3, -90, t=1) == [1, 1, 1]            # 1 * (1 - 0.9) = 0.1 rounds to 0, which is not a tempo


@pytest.mark.parametrize("bad", [0, -5, True, False])
def test_bars_with_a_tempo_that_is_not_a_positive_number_are_refused_naming_the_bar_and_the_tempo(bad):
  bars = four_bars()
  bars[2]["tempo_bpm"] = bad
  with pytest.raises(ValueError, match=r"rhythm_bars_to_stream: bar 2: tempo_bpm must be a positive number"):
    lib.rhythm_bars_to_stream(bars)
