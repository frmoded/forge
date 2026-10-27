"""2026-10-27-1030 (score-first M14 slice 1, design 4.13): thin_out_bars / double_up_bars - two pure, deterministic REGION transforms over a list of bars.

Both take the list of rhythm-data bars the other phrase functions return (extend_rhythm, morph_rhythm), a 1-based inclusive range `first`..`last`, and an optional row
(a channel name). Every bar outside the range is returned unchanged; the inputs are never mutated and the result shares no list with them.

thin_out_bars removes round-half-up(amount * hits) hits from each targeted row of each bar in the range. keep="downbeat" keeps the metrically strongest hits (strength 3 at
step 0, 2 at the other group starts, 1 at a group's midpoint, 0 elsewhere - the strength morph_rhythm's musical order uses; ties keep the EARLIER step); keep="seeded" removes
a deterministic shuffle of the hits, driven by `seed`. It never adds a hit.

double_up_bars gives every hit a second hit one step later (the same value: plain true or the same velocity) when that step is a rest in the ORIGINAL row and the bar has one;
the grid argument names the step count the region must have. It never removes a hit.

Hand-worked pins on the 16-step grid (group_size 4), bars 1 and 2 below:
  bar 1  kick [0, 4, 8, 12]  snare [4, 12]  hihat [0, 2, 4, 6, 8, 10, 12, 14]
  bar 2  kick [0, 3, 8, 10]  snare [4, 12]
"""
import copy
import random

import pytest

from forge.music import lib


def _bar(tempo=100, swing=0, steps=16, group=4, **channels):
  out = {"time_signature": "4/4", "steps": steps, "group_size": group, "swing_pct": swing, "tempo_bpm": tempo, "channels": {}}
  for name, at in channels.items():
    if isinstance(at, (set, list, tuple)):
      at = {i: True for i in at}
    out["channels"][name] = [at.get(i, False) for i in range(steps)]
  return out


def _fixture():
  return [
    _bar(tempo=100, kick={0, 4, 8, 12}, snare={4, 12}, hihat={0, 2, 4, 6, 8, 10, 12, 14}),
    _bar(tempo=90, kick={0, 3, 8, 10}, snare={4, 12}),
  ]


def _hits(bar, channel):
  return [i for i, v in enumerate(bar["channels"][channel]) if v is not False and v != 0]


# ---- thin_out_bars: the hand-worked pins ---------------------------------------------------------------------------------------------------------------------------------------------

def test_thin_out_one_row_of_one_bar_keeps_the_strongest_hits():
  # bar 2 kick [0, 3, 8, 10]: strengths 3, 0, 2, 1 -> ranked 0, 8, 10, 3; amount 0.5 removes round-half-up(2.0) = 2 -> the two weakest: 10 and 3
  out = lib.thin_out_bars(_fixture(), 2, 2, row="kick", keep="downbeat", amount=0.5)
  assert _hits(out[1], "kick") == [0, 8]
  assert _hits(out[1], "snare") == [4, 12], "another row of the same bar is untouched"
  assert out[0] == _fixture()[0], "a bar outside the range is unchanged"


def test_thin_out_amount_is_round_half_up_of_the_hit_count():
  # amount 0.25 of 4 hits = 1.0 -> remove 1 (the weakest, step 3); 0.125 of 4 = 0.5 -> rounds UP to 1; 0.1 of 4 = 0.4 -> 0
  assert _hits(lib.thin_out_bars(_fixture(), 2, 2, row="kick", amount=0.25)[1], "kick") == [0, 8, 10]
  assert _hits(lib.thin_out_bars(_fixture(), 2, 2, row="kick", amount=0.125)[1], "kick") == [0, 8, 10]
  assert _hits(lib.thin_out_bars(_fixture(), 2, 2, row="kick", amount=0.1)[1], "kick") == [0, 3, 8, 10]
  assert _hits(lib.thin_out_bars(_fixture(), 2, 2, row="kick", amount=1)[1], "kick") == []
  assert _hits(lib.thin_out_bars(_fixture(), 2, 2, row="kick", amount=0)[1], "kick") == [0, 3, 8, 10]


def test_thin_out_without_a_row_thins_every_row_of_every_bar_in_the_range():
  out = lib.thin_out_bars(_fixture(), 1, 1, amount=0.5)
  # kick [0, 4, 8, 12]: strengths 3, 2, 2, 2 -> remove 2: the latest of the equal ones (12, 8) -> [0, 4]
  assert _hits(out[0], "kick") == [0, 4]
  # snare [4, 12]: strengths 2, 2 -> remove 1: the later one -> [4]
  assert _hits(out[0], "snare") == [4]
  # hihat: 8 hits, remove 4: the four midpoints (strength 1) -> [0, 4, 8, 12]
  assert _hits(out[0], "hihat") == [0, 4, 8, 12]
  assert out[1] == _fixture()[1]


def test_thin_out_over_a_range_of_two_bars():
  out = lib.thin_out_bars(_fixture(), 1, 2, row="snare", amount=0.5)
  assert _hits(out[0], "snare") == [4] and _hits(out[1], "snare") == [4]
  assert _hits(out[0], "kick") == [0, 4, 8, 12] and _hits(out[1], "kick") == [0, 3, 8, 10]


def test_thin_out_keeps_the_velocity_of_a_surviving_hit_and_everything_else_of_the_bar():
  bars = _fixture()
  bars[1]["channels"]["kick"][0] = 110
  bars[1]["channels"]["kick"][8] = 70
  out = lib.thin_out_bars(bars, 2, 2, row="kick", amount=0.5)
  assert out[1]["channels"]["kick"][0] == 110 and out[1]["channels"]["kick"][8] == 70
  assert out[1]["tempo_bpm"] == 90 and out[1]["swing_pct"] == 0 and out[1]["steps"] == 16 and out[1]["group_size"] == 4


def test_thin_out_seeded_is_deterministic_and_the_seed_matters():
  a = lib.thin_out_bars(_fixture(), 1, 1, row="hihat", keep="seeded", amount=0.5, seed=1)
  b = lib.thin_out_bars(_fixture(), 1, 1, row="hihat", keep="seeded", amount=0.5, seed=1)
  assert a == b
  seen = {tuple(_hits(lib.thin_out_bars(_fixture(), 1, 1, row="hihat", keep="seeded", amount=0.5, seed=s)[0], "hihat")) for s in range(12)}
  assert len(seen) > 1, "different seeds thin differently"
  for hits in seen:
    assert len(hits) == 4 and set(hits) <= {0, 2, 4, 6, 8, 10, 12, 14}


# ---- double_up_bars: the hand-worked pins ---------------------------------------------------------------------------------------------------------------------------------------------

def test_double_up_gives_every_hit_a_second_one_a_step_later_where_the_step_is_free():
  out = lib.double_up_bars(_fixture(), 2, 2, row="kick", grid=16)
  # kick [0, 3, 8, 10] -> 1, 4, 9, 11 are free in the original row
  assert _hits(out[1], "kick") == [0, 1, 3, 4, 8, 9, 10, 11]
  assert _hits(out[1], "snare") == [4, 12]
  assert out[0] == _fixture()[0]


def test_double_up_never_lands_on_a_hit_and_never_runs_off_the_bar():
  bar = _bar(kick={4, 5, 15})
  out = lib.double_up_bars([bar], 1, 1, row="kick")
  # 4 -> 5 is a hit already (skipped); 5 -> 6; 15 -> 16 does not exist
  assert _hits(out[0], "kick") == [4, 5, 6, 15]


def test_double_up_copies_the_velocity_and_works_from_the_original_row_not_from_its_own_additions():
  bar = _bar(kick={0})
  bar["channels"]["kick"][0] = 90
  bar["channels"]["kick"][1] = False
  out = lib.double_up_bars([bar], 1, 1, row="kick")
  assert out[0]["channels"]["kick"][:3] == [90, 90, False], "one doubling per hit: the new hit is not doubled again"


def test_double_up_without_a_row_doubles_every_row_in_the_range_only():
  out = lib.double_up_bars(_fixture(), 2, 2)
  assert _hits(out[1], "snare") == [4, 5, 12, 13]
  assert out[0] == _fixture()[0]


# ---- refusals: the same kind as the other functions' (ValueError naming the function) ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("first,last", [(0, 1), (1, 3), (2, 1), (-1, 2), (1.0, 2), ("1", 2), (True, 2), (1, None)])
def test_a_bad_range_is_refused_naming_the_function_and_the_bar_count(first, last):
  for fn in (lib.thin_out_bars, lib.double_up_bars):
    with pytest.raises(ValueError, match=fn.__name__):
      fn(_fixture(), first, last)
  with pytest.raises(ValueError, match="2 bars"):
    lib.thin_out_bars(_fixture(), first, last)


@pytest.mark.parametrize("bars", [[], None, "bar", {}, [None], [{"steps": 16}]])
def test_bars_must_be_a_non_empty_list_of_rhythm_data(bars):
  with pytest.raises(ValueError, match="thin_out_bars"):
    lib.thin_out_bars(bars, 1, 1)
  with pytest.raises(ValueError, match="double_up_bars"):
    lib.double_up_bars(bars, 1, 1)


def test_a_row_that_a_bar_in_the_range_does_not_have_is_refused_naming_the_row_and_the_bar():
  bars = _fixture()
  with pytest.raises(ValueError, match=r"row 'hihat'.*bar 2"):
    lib.thin_out_bars(bars, 1, 2, row="hihat")
  with pytest.raises(ValueError, match=r"row 'cowbell'.*bar 1"):
    lib.double_up_bars(bars, 1, 1, row="cowbell")
  # a bar OUTSIDE the range may lack the row
  assert lib.thin_out_bars(bars, 1, 1, row="hihat")[1] == bars[1]
  with pytest.raises(ValueError, match="row"):
    lib.thin_out_bars(bars, 1, 1, row=3)
  with pytest.raises(ValueError, match="row"):
    lib.thin_out_bars(bars, 1, 1, row="")


@pytest.mark.parametrize("amount", [-0.1, 1.1, "half", None, True, float("nan")])
def test_thin_out_amount_must_be_a_number_from_0_to_1(amount):
  with pytest.raises(ValueError, match="thin_out_bars: amount"):
    lib.thin_out_bars(_fixture(), 1, 1, amount=amount)


def test_thin_out_keep_and_seed_are_checked():
  with pytest.raises(ValueError, match=r"thin_out_bars: keep must be one of \['downbeat', 'seeded'\]"):
    lib.thin_out_bars(_fixture(), 1, 1, keep="loudest")
  for seed in (-1, 1.5, "1", True, None):
    with pytest.raises(ValueError, match="thin_out_bars: seed"):
      lib.thin_out_bars(_fixture(), 1, 1, seed=seed)


def test_double_up_grid_must_be_the_step_count_of_every_bar_in_the_range():
  with pytest.raises(ValueError, match=r"double_up_bars: bar 2 has 8 steps, but grid is 16"):
    lib.double_up_bars([_bar(kick={0}), _bar(steps=8, kick={0})], 1, 2, grid=16)
  assert lib.double_up_bars([_bar(kick={0}), _bar(steps=8, kick={0})], 1, 1, grid=16)[1]["steps"] == 8, "a bar outside the range may have another grid"
  for grid in (0, -4, 1.5, "16", True, None):
    with pytest.raises(ValueError, match="double_up_bars: grid"):
      lib.double_up_bars(_fixture(), 1, 1, grid=grid)


def test_an_unusable_bar_in_the_region_is_the_enginess_own_refusal_naming_the_function():
  bad = _fixture()
  bad[1]["channels"]["kick"][2] = 200
  with pytest.raises(ValueError, match=r"thin_out_bars: .*invalid step value"):
    lib.thin_out_bars(bad, 2, 2)
  with pytest.raises(ValueError, match=r"double_up_bars: .*invalid step value"):
    lib.double_up_bars(bad, 2, 2)
  with pytest.raises(ValueError, match="unknown channel"):
    lib.thin_out_bars([_bar(kazoo={0})], 1, 1)


# ---- purity and properties ------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_inputs_are_never_mutated_and_the_result_shares_no_list_with_them():
  bars = _fixture()
  before = copy.deepcopy(bars)
  for out in (lib.thin_out_bars(bars, 1, 2, amount=0.5), lib.double_up_bars(bars, 1, 2)):
    assert bars == before
    for original, made in zip(bars, out):
      assert made is not original
      for name in made["channels"]:
        if name in original["channels"]:
          assert made["channels"][name] is not original["channels"][name]


def test_the_result_has_as_many_bars_as_the_input_and_a_range_over_everything_is_fine():
  bars = _fixture()
  assert len(lib.thin_out_bars(bars, 1, 2)) == 2 and len(lib.double_up_bars(bars, 1, 2)) == 2
  assert lib.thin_out_bars(bars, 1, 2, amount=0) == bars
  assert lib.thin_out_bars(bars, 1, 1, amount=0) == bars


def _random_bars(rng):
  n = rng.randint(1, 5)
  bars = []
  for _ in range(n):
    steps = 16
    chans = {}
    for name in rng.sample(["kick", "snare", "hihat", "bell"], rng.randint(1, 4)):
      row = []
      for _s in range(steps):
        r = rng.random()
        row.append(False if r < 0.6 else (True if r < 0.85 else rng.randint(1, 127)))
      chans[name] = row
    bars.append({"time_signature": "4/4", "steps": steps, "group_size": 4, "swing_pct": rng.choice([0, 20]), "tempo_bpm": rng.choice([80, 100, 140]), "channels": chans})
  return bars


def _hit_cells(bar):
  return {(c, i) for c, row in bar["channels"].items() for i, v in enumerate(row) if v is not False and v != 0}


def test_properties_over_random_bars_outside_unchanged_thin_never_adds_double_never_removes():
  rng = random.Random(20261027)
  for _ in range(300):
    bars = _random_bars(rng)
    n = len(bars)
    first = rng.randint(1, n)
    last = rng.randint(first, n)
    common = set.intersection(*(set(b["channels"]) for b in bars[first - 1:last]))
    row = rng.choice([None] + sorted(common)) if common else None
    for fn, kw in ((lib.thin_out_bars, {"keep": rng.choice(["downbeat", "seeded"]), "amount": rng.choice([0, 0.25, 0.5, 0.75, 1]), "seed": rng.randint(0, 9)}), (lib.double_up_bars, {})):
      out = fn(bars, first, last, row=row, **kw)
      assert len(out) == n
      for i in range(n):
        inside = first - 1 <= i <= last - 1
        if not inside:
          assert out[i] == bars[i], f"{fn.__name__}: bar {i + 1} is outside the range"
          continue
        before, after = _hit_cells(bars[i]), _hit_cells(out[i])
        if fn is lib.thin_out_bars:
          assert after <= before, "thin_out never adds a hit"
        else:
          assert before <= after, "double_up never removes a hit"
        if row is not None:
          for name in bars[i]["channels"]:
            if name != row:
              assert out[i]["channels"][name] == bars[i]["channels"][name], "a row that was not asked for is untouched"
        for name, vals in bars[i]["channels"].items():
          for s, v in enumerate(vals):
            if v is not False and v != 0 and out[i]["channels"][name][s] is not False and out[i]["channels"][name][s] != 0:
              assert out[i]["channels"][name][s] == v or fn is lib.double_up_bars, "a surviving hit keeps its velocity"


def test_property_thin_out_removes_exactly_round_half_up_of_the_hits_per_targeted_row():
  rng = random.Random(7)
  for _ in range(200):
    bars = _random_bars(rng)
    amount = rng.choice([0, 0.1, 0.25, 0.3, 0.5, 0.75, 1])
    out = lib.thin_out_bars(bars, 1, len(bars), amount=amount, keep=rng.choice(["downbeat", "seeded"]), seed=rng.randint(0, 5))
    for b, o in zip(bars, out):
      for name in b["channels"]:
        n_before = len(_hit_cells({"channels": {name: b["channels"][name]}}))
        n_after = len(_hit_cells({"channels": {name: o["channels"][name]}}))
        assert n_before - n_after == int(amount * n_before + 0.5)


# ---- edges found by the mutation pass --------------------------------------------------------------------------------------------------------------------------------------------

def test_the_refusal_for_no_bars_and_for_a_bad_row_says_what_is_wrong():
  with pytest.raises(ValueError, match="bars must be a non-empty list"):
    lib.thin_out_bars([], 1, 1)
  with pytest.raises(ValueError, match="bars must be a non-empty list"):
    lib.double_up_bars([], 1, 1)
  for bad in ("", 3, ["kick"]):
    with pytest.raises(ValueError, match="row must be a channel name"):
      lib.thin_out_bars(_fixture(), 1, 1, row=bad)
    with pytest.raises(ValueError, match="row must be a channel name"):
      lib.double_up_bars(_fixture(), 1, 1, row=bad)


def test_a_group_size_of_zero_is_refused_not_divided_by():
  bars = _fixture()
  bars[0]["group_size"] = 0
  with pytest.raises(ValueError, match="bar 1 group_size must be a positive int"):
    lib.thin_out_bars(bars, 1, 1)
  with pytest.raises(ValueError, match="bar 1 group_size must be a positive int"):
    lib.double_up_bars(bars, 1, 1)
  assert lib.thin_out_bars(bars, 2, 2)[0]["group_size"] == 0, "a bar outside the range is not looked at"


def test_seeded_thinning_is_not_the_same_shuffle_for_every_bar_and_row():
  twin = [_bar(hihat={0, 2, 4, 6, 8, 10, 12, 14}, snare={0, 2, 4, 6, 8, 10, 12, 14}) for _ in range(2)]
  differs_between_bars, differs_between_rows = False, False
  for seed in range(8):
    out = lib.thin_out_bars(twin, 1, 2, keep="seeded", amount=0.5, seed=seed)
    differs_between_bars = differs_between_bars or _hits(out[0], "hihat") != _hits(out[1], "hihat")
    differs_between_rows = differs_between_rows or _hits(out[0], "hihat") != _hits(out[0], "snare")
  assert differs_between_bars and differs_between_rows


def test_double_up_never_overwrites_a_hit_that_has_its_own_velocity():
  bar = _bar(kick={4, 5})
  bar["channels"]["kick"][4] = 100
  bar["channels"]["kick"][5] = 60
  out = lib.double_up_bars([bar], 1, 1, row="kick")
  assert out[0]["channels"]["kick"][4:7] == [100, 60, 60], "step 5 keeps its own 60; step 6 is the doubling of step 5"


def test_double_up_leaves_a_rest_exactly_as_it_was_whatever_form_the_rest_is_written_in():
  bar = _bar(kick={0})
  bar["channels"]["kick"][1] = 0          # a rest written as 0
  bar["channels"]["kick"][2] = False      # a rest written as false
  out = lib.double_up_bars([bar], 1, 1, row="kick")
  row = out[0]["channels"]["kick"]
  assert row[0] is True and row[1] is True, "the hit and its doubling"
  assert row[2] is False, "the rest after a rest is untouched (the same False, not a copy of the 0 before it)"
