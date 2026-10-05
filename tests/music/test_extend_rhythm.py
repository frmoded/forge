"""Beat-as-data Phase 4 (drain 2026-10-05-2100): extend_rhythm (three named styles) + rhythm_bars_to_stream.

Hand-worked pins come from the actual seed JSON (music-theory/rhythm_data/rhythm_pattern_straight_rock.md):
  kick  [0, 8]   snare [4, 12]   hihat [0, 2, 4, 6, 8, 10, 12, 14]   (16 steps, 4/4, 100 BPM)"""
import copy

import pytest
from music21 import articulations as m21_articulations

from forge.music import lib


def _rock():
  return {
    "time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100,
    "channels": {
      "kick":  [i in (0, 8) for i in range(16)],
      "snare": [i in (4, 12) for i in range(16)],
      "hihat": [i % 2 == 0 for i in range(16)],
    },
  }


def _synco():
  return {
    "time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100,
    "channels": {
      "kick":  [i in (0, 3, 10) for i in range(16)],
      "snare": [i in (7, 12) for i in range(16)],
      "hihat": [i in (2, 6, 10, 14) for i in range(16)],
    },
  }


def _hits(steps):
  """{step index: value} for the hit steps of one channel."""
  return {i: v for i, v in enumerate(steps) if v is not False and v != 0}


FILL = [64, 80, 96, 112]


# ---- repeat_with_fills --------------------------------------------------------------------------------

def test_fills_four_bars_only_bar_three_is_filled_hand_worked():
  bars = lib.extend_rhythm(_rock(), bars=4, style="repeat_with_fills")
  assert len(bars) == 4
  for i in (0, 1, 2):
    assert bars[i] == _rock(), f"bar {i} must be an untouched copy of the seed"
  fill = bars[3]["channels"]
  assert _hits(fill["kick"]) == {0: True, 8: True}                         # seed kick, steps 12-15 cleared (none there)
  assert fill["snare"][12:16] == FILL and fill["snare"][4] is True         # fill REPLACES the snare's plain true on 12
  assert _hits(fill["hihat"]) == {0: True, 2: True, 4: True, 6: True, 8: True, 10: True}   # hi-hat 12 and 14 cleared


@pytest.mark.parametrize("n, filled", [(1, [0]), (2, [1]), (3, [2]), (4, [3]), (5, [3, 4]), (6, [3, 5]), (7, [3, 6]), (8, [3, 7])])
def test_fills_land_where_i_plus_one_is_a_multiple_of_four_or_on_the_last_bar(n, filled):
  bars = lib.extend_rhythm(_rock(), bars=n, style="repeat_with_fills")
  assert [i for i, b in enumerate(bars) if b["channels"]["snare"][12:16] == FILL] == filled


def test_fills_clear_kick_and_hihat_on_the_last_beat_even_when_the_seed_has_them_there():
  seed = _rock()
  seed["channels"]["kick"] = [i in (0, 12, 14) for i in range(16)]
  seed["channels"]["hihat"] = [True] * 16
  fill = lib.extend_rhythm(seed, bars=1, style="repeat_with_fills")[0]["channels"]
  assert fill["kick"][12:16] == [False] * 4 and fill["hihat"][12:16] == [False] * 4
  assert fill["kick"][:12] == seed["channels"]["kick"][:12]              # everything before step 12 is the seed's
  assert fill["hihat"][:12] == [True] * 12


def test_fills_create_a_missing_snare_in_every_bar_and_never_invent_a_kick_or_hihat():
  seed = _rock()
  del seed["channels"]["snare"]
  del seed["channels"]["kick"]
  bars = lib.extend_rhythm(seed, bars=4, style="repeat_with_fills")
  for b in bars:
    assert list(b["channels"]) == ["hihat", "snare"]                     # same channel set in every bar (sequence needs it)
  assert bars[0]["channels"]["snare"] == [False] * 16                    # non-fill bar: the created snare is all rest
  assert bars[3]["channels"]["snare"][12:16] == FILL


# ---- building -----------------------------------------------------------------------------------------

def _building_hat(bar_index):
  return lib.extend_rhythm(_rock(), bars=4, style="building")[bar_index]["channels"]["hihat"]


def test_building_bar_zero_is_quarter_notes_at_velocity_80_hand_worked():
  assert _hits(_building_hat(0)) == {0: 80, 4: 80, 8: 80, 12: 80}


def test_building_bar_one_is_eighths_alternating_80_and_56_by_step_mod_4():
  assert _hits(_building_hat(1)) == {0: 80, 2: 56, 4: 80, 6: 56, 8: 80, 10: 56, 12: 80, 14: 56}


@pytest.mark.parametrize("bar_index", [2, 3])
def test_building_from_bar_two_is_sixteenths_80_on_the_beat_else_56(bar_index):
  assert _building_hat(bar_index) == [80 if i % 4 == 0 else 56 for i in range(16)]


def test_building_keeps_kick_and_snare_from_the_seed_and_ignores_the_seeds_hihat():
  seed = _rock()
  seed["channels"]["hihat"] = [True] * 16                                # a different seed hi-hat...
  a = lib.extend_rhythm(seed, bars=4, style="building")
  b = lib.extend_rhythm(_rock(), bars=4, style="building")
  assert [x["channels"]["hihat"] for x in a] == [x["channels"]["hihat"] for x in b]   # ...changes nothing
  for bar in a:
    assert bar["channels"]["kick"] == seed["channels"]["kick"]
    assert bar["channels"]["snare"] == seed["channels"]["snare"]


def test_building_hihat_velocities_never_reach_the_accent_threshold():
  for bar in lib.extend_rhythm(_rock(), bars=8, style="building"):
    assert max(v for v in bar["channels"]["hihat"] if v) < lib._RHYTHM_ACCENT_THRESHOLD


def test_building_creates_the_hihat_when_the_seed_has_none():
  seed = _rock()
  del seed["channels"]["hihat"]
  assert _hits(lib.extend_rhythm(seed, bars=1, style="building")[0]["channels"]["hihat"]) == {0: 80, 4: 80, 8: 80, 12: 80}


# ---- ghost_notes --------------------------------------------------------------------------------------

def _ghost_snare(bar_index, seed=None):
  return lib.extend_rhythm(seed or _rock(), bars=4, style="ghost_notes")[bar_index]["channels"]["snare"]


def test_ghost_notes_even_bars_use_steps_3_7_11_15_odd_bars_1_5_9_13_hand_worked():
  assert _hits(_ghost_snare(0)) == {3: 36, 4: True, 7: 36, 11: 36, 12: True, 15: 36}
  assert _hits(_ghost_snare(1)) == {1: 36, 4: True, 5: 36, 9: 36, 12: True, 13: 36}
  assert _hits(_ghost_snare(2)) == _hits(_ghost_snare(0))
  assert _hits(_ghost_snare(3)) == _hits(_ghost_snare(1))


def test_ghost_notes_never_land_on_a_seed_snare_or_kick_hit_and_seed_hits_stay_exactly_as_they_were():
  seed = _rock()
  seed["channels"]["snare"] = [i in (3, 4) for i in range(16)]           # 3 is an even-bar ghost step
  seed["channels"]["kick"] = [i in (7, 9) for i in range(16)]            # 7 even-bar ghost step, 9 odd-bar ghost step
  seed["channels"]["snare"][5] = 100                                      # an int seed hit: must stay 100, not 36
  even = _ghost_snare(0, seed)
  assert even[3] is True and even[7] is False                             # seed snare on 3 kept as plain True; kick-covered 7 skipped
  assert _hits(even) == {3: True, 4: True, 5: 100, 11: 36, 15: 36}
  odd = _ghost_snare(1, seed)
  assert odd[5] == 100 and odd[9] is False                                # seed snare on 5 kept; kick-covered 9 skipped
  assert _hits(odd) == {1: 36, 3: True, 4: True, 5: 100, 13: 36}


def test_ghost_notes_leave_kick_and_hihat_untouched_and_create_a_missing_snare():
  bars = lib.extend_rhythm(_rock(), bars=2, style="ghost_notes")
  for b in bars:
    assert b["channels"]["kick"] == _rock()["channels"]["kick"] and b["channels"]["hihat"] == _rock()["channels"]["hihat"]
  seed = _rock()
  del seed["channels"]["snare"]
  assert _hits(lib.extend_rhythm(seed, bars=1, style="ghost_notes")[0]["channels"]["snare"]) == {3: 36, 7: 36, 11: 36, 15: 36}


def test_ghost_velocity_is_below_the_accent_threshold_so_ghosts_are_never_marked():
  for bar in lib.extend_rhythm(_rock(), bars=4, style="ghost_notes"):
    assert 36 < lib._RHYTHM_ACCENT_THRESHOLD


# ---- contract shared by all styles --------------------------------------------------------------------

STYLES = ["repeat_with_fills", "building", "ghost_notes"]


@pytest.mark.parametrize("style", STYLES)
def test_returns_one_new_dict_per_bar_keeping_every_top_level_field(style):
  seed = _rock()
  seed.update(swing_pct=25, tempo_bpm=87)
  bars = lib.extend_rhythm(seed, bars=5, style=style)
  assert isinstance(bars, list) and len(bars) == 5
  for b in bars:
    assert isinstance(b, dict)
    assert {k: b[k] for k in ("time_signature", "steps", "group_size", "swing_pct", "tempo_bpm")} == \
           {"time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 25, "tempo_bpm": 87}


@pytest.mark.parametrize("style", STYLES)
def test_input_is_never_mutated_and_no_list_is_shared_between_bars_or_with_the_seed(style):
  seed = _rock()
  before = copy.deepcopy(seed)
  bars = lib.extend_rhythm(seed, bars=4, style=style)
  assert seed == before
  lists = [id(seed["channels"])] + [id(seed["channels"][c]) for c in seed["channels"]]
  for b in bars:
    lists.append(id(b["channels"]))
    lists.extend(id(v) for v in b["channels"].values())
  assert len(lists) == len(set(lists)), "a channel list or channels dict is shared"
  bars[0]["channels"]["kick"][0] = "poison"
  assert seed == before and bars[1]["channels"]["kick"][0] is True


@pytest.mark.parametrize("style", STYLES)
def test_every_bar_has_the_same_channel_set_so_sequencing_by_position_lines_up(style):
  seed = _rock()
  del seed["channels"]["snare"]
  keysets = {tuple(b["channels"]) for b in lib.extend_rhythm(seed, bars=4, style=style)}
  assert len(keysets) == 1


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("kw", [
  {"time_signature": "3/4", "steps": 12},                                 # 3/4 in sixteenths
  {"steps": 8, "group_size": 2},                                           # an 8-step grid
  {"group_size": 2},                                                       # 16 steps but not 4 per group
  {"steps": 32, "group_size": 4},
])
def test_non_16_step_grids_are_rejected_with_a_message_saying_so(style, kw):
  d = _rock()
  steps = kw.get("steps", 16)
  d.update(kw)
  d["channels"] = {c: v[:steps] + [False] * (steps - len(v[:steps])) for c, v in d["channels"].items()}
  with pytest.raises(ValueError, match=r"extend_rhythm.*16"):
    lib.extend_rhythm(d, bars=4, style=style)


@pytest.mark.parametrize("bad", ["swing", "", None, 3, "REPEAT_WITH_FILLS", "fills"])
def test_unknown_style_lists_the_valid_names(bad):
  with pytest.raises(ValueError) as e:
    lib.extend_rhythm(_rock(), bars=4, style=bad)
  for name in STYLES:
    assert name in str(e.value)


@pytest.mark.parametrize("bad", [0, -1, 65, 1000, True, False, 1.5, 4.0, "4", None])
def test_bars_must_be_an_int_from_1_to_64_and_bool_is_rejected(bad):
  with pytest.raises(ValueError, match=r"extend_rhythm.*bars"):
    lib.extend_rhythm(_rock(), bars=bad, style="building")


@pytest.mark.parametrize("n", [1, 64])
def test_bars_bounds_are_inclusive(n):
  assert len(lib.extend_rhythm(_rock(), bars=n, style="building")) == n


def test_default_arguments_are_four_bars_of_repeat_with_fills():
  assert lib.extend_rhythm(_rock()) == lib.extend_rhythm(_rock(), bars=4, style="repeat_with_fills")


def test_bad_seed_is_rejected_with_the_function_name():
  with pytest.raises(ValueError, match="extend_rhythm"):
    lib.extend_rhythm("nope", bars=4, style="building")
  bad = _rock()
  bad["channels"]["kick"][3] = "x"
  with pytest.raises(ValueError, match=r"extend_rhythm.*'kick'.*step 3"):
    lib.extend_rhythm(bad, bars=4, style="building")
  bad = _rock()
  bad["channels"]["cowbell"] = [False] * 16
  with pytest.raises(ValueError, match="cowbell"):
    lib.extend_rhythm(bad, bars=4, style="building")


def test_both_new_functions_are_registered_as_music_chips_in_both_executor_lists():
  from forge.core import executor
  for name in ("extend_rhythm", "rhythm_bars_to_stream"):
    assert callable(executor._domain_globals_for(["music"])[name])
    assert executor._FORGE_MUSIC_LIB_NAMES[name].__name__ == name
    assert name in executor._MUSIC_LAZY_CHIP_NAMES


# ---- rhythm_bars_to_stream ----------------------------------------------------------------------------

def _midi_ons(score):
  """[(offset, drum slot, velocity)] over every part, via a real MIDI write + parse."""
  import os
  import tempfile
  from music21 import converter
  fp = os.path.join(tempfile.mkdtemp(), "x.mid")
  score.write("midi", fp=fp)
  return sorted((float(n.offset), n.storedInstrument.percMapPitch, n.volume.velocity)
                for n in converter.parse(fp).flatten().notes)


def test_bars_to_stream_one_part_per_channel_one_measure_per_bar_in_order():
  bars = lib.extend_rhythm(_rock(), bars=4, style="repeat_with_fills")
  score = lib.rhythm_bars_to_stream(bars)
  assert [p.getInstrument().instrumentName for p in score.parts] == ["Kick", "Snare", "Closed Hi-Hat"]
  assert [len(p.getElementsByClass("Measure")) for p in score.parts] == [4, 4, 4]
  snare = score.parts[1].flatten().notes
  # bars 0-2 (4 quarters each): snare on steps 4 and 12 -> offsets 1, 3 / 5, 7 / 9, 11. Bar 3 starts at 12.0: its snare is
  # step 4 (-> 13.0) plus the fill on steps 12-15 (-> 15.0, 15.25, 15.5, 15.75).
  assert [float(n.offset) for n in snare] == [1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0, 15.0, 15.25, 15.5, 15.75]
  assert [n.volume.velocity for n in snare][-4:] == FILL


def test_bars_to_stream_orders_bars_exactly_as_given():
  rock, synco = lib.rhythm_data_to_stream(_rock()), lib.rhythm_data_to_stream(_synco())
  a = lib.rhythm_bars_to_stream([_rock(), _synco()])
  b = lib.rhythm_bars_to_stream([_synco(), _rock()])
  kick_a = [float(n.offset) for n in a.parts[0].flatten().notes]
  kick_b = [float(n.offset) for n in b.parts[0].flatten().notes]
  assert kick_a == [0.0, 2.0, 4.0, 4.75, 6.5]                              # rock bar, then syncopated bar
  assert kick_b == [0.0, 0.75, 2.5, 4.0, 6.0]                              # syncopated bar, then rock bar
  assert kick_a != kick_b


def test_bars_to_stream_with_one_bar_is_the_same_notes_as_rhythm_data_to_stream():
  one = lib.rhythm_bars_to_stream([_rock()])
  direct = lib.rhythm_data_to_stream(_rock())
  assert _midi_ons(one) == _midi_ons(direct)
  assert [p.getInstrument().instrumentName for p in one.parts] == [p.getInstrument().instrumentName for p in direct.parts]


def test_bars_to_stream_note_on_events_equal_the_per_bar_converter_output_laid_end_to_end():
  bars = lib.extend_rhythm(_rock(), bars=3, style="ghost_notes")
  whole = _midi_ons(lib.rhythm_bars_to_stream(bars))
  expect = []
  for i, b in enumerate(bars):
    expect.extend((off + 4.0 * i, slot, vel) for off, slot, vel in _midi_ons(lib.rhythm_data_to_stream(b)))
  assert whole == sorted(expect)


def test_bars_to_stream_composes_with_accent_mask_and_keeps_the_accent_marks():
  accented = lib.accent_mask(_rock(), _synco())
  score = lib.rhythm_bars_to_stream([accented, accented])
  counts = [sum(any(isinstance(a, m21_articulations.Accent) for a in n.articulations) for n in p.flatten().notes)
            for p in score.parts]
  assert counts == [2, 2, 12]                                              # 1 + 1 + 6 per bar, two bars
  assert [v for _, slot, v in _midi_ons(score) if slot == 38] == [72, 112, 72, 112]   # velocities exact, in order


def test_bars_to_stream_pads_a_channel_missing_from_some_bars_so_staves_line_up():
  only_kick = {**_rock(), "channels": {"kick": _rock()["channels"]["kick"]}}
  score = lib.rhythm_bars_to_stream([only_kick, _rock()])
  assert [p.getInstrument().instrumentName for p in score.parts] == ["Kick", "Snare", "Closed Hi-Hat"]
  assert [len(p.getElementsByClass("Measure")) for p in score.parts] == [2, 2, 2]
  assert len(score.parts[1].flatten().notes) == 2                           # snare only sounds in bar 2


def test_bars_to_stream_pads_a_MIDDLE_channel_too_because_sequence_groups_staves_by_position():
  """sequence() pads a missing channel only when it is the LAST position. A channel missing from the MIDDLE would shift
  the hi-hat into the snare's slot and split the staves, so the converter list is padded to the union first."""
  no_snare = {**_rock(), "channels": {"kick": _rock()["channels"]["kick"], "hihat": _rock()["channels"]["hihat"]}}
  score = lib.rhythm_bars_to_stream([no_snare, _rock()])
  # first-seen channel order across the bars: kick, hihat (bar 0), then snare (bar 1) — one stave per instrument, none split
  assert [p.getInstrument().instrumentName for p in score.parts] == ["Kick", "Closed Hi-Hat", "Snare"]
  assert [len(p.getElementsByClass("Measure")) for p in score.parts] == [2, 2, 2]


@pytest.mark.parametrize("bad", [[], (), "bars", None, 5, {"a": 1}])
def test_bars_to_stream_needs_a_non_empty_list(bad):
  with pytest.raises(ValueError, match="rhythm_bars_to_stream"):
    lib.rhythm_bars_to_stream(bad)


def test_bars_to_stream_rejects_a_non_dict_bar_and_names_its_index():
  with pytest.raises(ValueError, match=r"rhythm_bars_to_stream.*bar 1"):
    lib.rhythm_bars_to_stream([_rock(), "nope"])


@pytest.mark.parametrize("field, value", [("time_signature", "3/4"), ("steps", 8), ("group_size", 2), ("tempo_bpm", 120)])
def test_bars_to_stream_rejects_bars_that_disagree_naming_the_first_mismatch(field, value):
  other = _rock()
  other[field] = value
  if field == "steps":
    other["channels"] = {c: v[:8] for c, v in other["channels"].items()}
  with pytest.raises(ValueError, match=rf"rhythm_bars_to_stream.*bar 1.*{field}"):
    lib.rhythm_bars_to_stream([_rock(), other])


def test_bars_to_stream_validates_every_bar_like_the_converter_and_names_the_bar():
  bad = _rock()
  bad["channels"]["snare"][2] = 128
  with pytest.raises(ValueError, match=r"rhythm_bars_to_stream.*bar 2.*'snare'.*step 2"):
    lib.rhythm_bars_to_stream([_rock(), _rock(), bad])


def test_bars_to_stream_does_not_mutate_its_input():
  bars = lib.extend_rhythm(_rock(), bars=4, style="repeat_with_fills")
  before = copy.deepcopy(bars)
  lib.rhythm_bars_to_stream(bars)
  assert bars == before
