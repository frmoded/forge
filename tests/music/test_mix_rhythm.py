"""Score-first M7 Phase A (drain 2026-10-22-2330): mix_rhythm — one bar as a weighted mix of two bars.

Hand-worked pins use two small bars on the 16-step grid (the same shapes as test_extend_rhythm):
  rock   kick [0, 8]       snare [4, 12]   hihat [0, 2, 4, 6, 8, 10, 12, 14]
  synco  kick [0, 3, 10]   snare [7, 12]   hihat [2, 6, 10, 14]"""
import copy

import pytest

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


def _bar(**channels):
  """A 16-step 4/4 bar whose channels are given as {step: value} dicts."""
  out = {"time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100, "channels": {}}
  for name, at in channels.items():
    out["channels"][name] = [at.get(i, False) for i in range(16)]
  return out


# ---- the two ends: weight 1 is a, weight 0 is b ---------------------------------------------------------

def test_weight_one_is_a_hits_and_plain_true():
  assert lib.mix_rhythm(_rock(), _synco(), weight=1) == _rock()


def test_weight_zero_is_b():
  assert lib.mix_rhythm(_rock(), _synco(), weight=0) == _synco()


def test_weight_one_keeps_a_velocities_even_where_b_has_a_louder_hit():
  a = _bar(kick={0: 64, 4: True}, snare={4: 100})
  b = _bar(kick={0: 127, 4: 110}, snare={4: True})
  out = lib.mix_rhythm(a, b, weight=1)
  assert out["channels"]["kick"] == a["channels"]["kick"]
  assert out["channels"]["snare"] == a["channels"]["snare"]
  assert out["channels"]["kick"][4] is True            # a's plain true stays plain


def test_weight_zero_keeps_b_velocities():
  a = _bar(kick={0: 64})
  b = _bar(kick={0: 127, 5: True})
  assert lib.mix_rhythm(a, b, weight=0)["channels"]["kick"] == b["channels"]["kick"]


def test_a_zero_int_step_is_a_rest_in_the_output():
  a = _bar(kick={0: True})
  a["channels"]["kick"][3] = 0
  out = lib.mix_rhythm(a, a, weight=0.5)
  assert out["channels"]["kick"][3] is False


# ---- 0.5 on a known pair, with the tie rule --------------------------------------------------------------

def test_half_and_half_keeps_shared_hits_and_places_single_bar_hits_at_the_tie():
  out = lib.mix_rhythm(_rock(), _synco(), weight=0.5, threshold=0.5)["channels"]
  # v = 0.5 for a hit in ONE bar, 1.0 for both; 0.5 >= 0.5 so every hit of either bar is placed (the union)
  assert set(_hits(out["kick"])) == {0, 3, 8, 10}
  assert set(_hits(out["snare"])) == {4, 7, 12}
  assert set(_hits(out["hihat"])) == {0, 2, 4, 6, 8, 10, 12, 14}
  assert all(v is True for ch in out.values() for v in _hits(ch).values())   # plain + plain stays plain


def test_threshold_just_above_the_tie_keeps_only_shared_hits():
  out = lib.mix_rhythm(_rock(), _synco(), weight=0.5, threshold=0.51)["channels"]
  assert set(_hits(out["kick"])) == {0}
  assert set(_hits(out["snare"])) == {12}
  assert set(_hits(out["hihat"])) == {2, 6, 10, 14}


def test_threshold_one_keeps_only_hits_both_bars_have_at_half_weight():
  out = lib.mix_rhythm(_rock(), _synco(), weight=0.5, threshold=1)["channels"]
  assert set(_hits(out["kick"])) == {0}


def test_threshold_zero_places_every_hit_of_either_bar_but_never_a_rest():
  out = lib.mix_rhythm(_rock(), _synco(), weight=0.5, threshold=0)["channels"]
  assert set(_hits(out["kick"])) == {0, 3, 8, 10}          # steps with no hit in either bar are NOT filled at threshold 0
  out0 = lib.mix_rhythm(_rock(), _synco(), weight=0, threshold=0)["channels"]
  assert out0["kick"] == _synco()["channels"]["kick"]       # weight 0, threshold 0 is still exactly b


def test_weight_point_three_threshold_edge_a_only_hit_is_in_at_its_own_weight():
  a = _bar(kick={0: True})
  b = _bar(kick={8: True})
  at = lib.mix_rhythm(a, b, weight=0.3, threshold=0.3)["channels"]["kick"]
  assert set(_hits(at)) == {0, 8}                           # a-only v = 0.3 >= 0.3 ; b-only v = 0.7 >= 0.3
  above = lib.mix_rhythm(a, b, weight=0.3, threshold=0.31)["channels"]["kick"]
  assert set(_hits(above)) == {8}                           # a-only drops out just above its weight
  b_edge = lib.mix_rhythm(a, b, weight=0.3, threshold=0.7)["channels"]["kick"]
  assert set(_hits(b_edge)) == {8}                          # b-only v = 0.7 >= 0.7
  past = lib.mix_rhythm(a, b, weight=0.3, threshold=0.71)["channels"]["kick"]
  assert _hits(past) == {}


@pytest.mark.parametrize("weight", [0.05 * k for k in range(21)])
def test_a_threshold_equal_to_a_slider_weight_is_never_lost_to_float_error(weight):
  # 1 - 0.9 is 0.09999999999999998 in floats; a hit sitting exactly at its own weight must still be placed.
  a = _bar(kick={0: True})
  b = _bar(kick={8: True})
  w = round(weight, 2)
  if w > 0:
    assert 0 in _hits(lib.mix_rhythm(a, b, weight=w, threshold=w)["channels"]["kick"])
  if w < 1:
    assert 8 in _hits(lib.mix_rhythm(a, b, weight=w, threshold=round(1 - w, 2))["channels"]["kick"])


# ---- velocity of a placed hit ----------------------------------------------------------------------------

def test_velocity_is_the_weighted_mean_of_the_bars_that_have_a_hit_rounded_half_up():
  a = _bar(kick={0: 100, 4: 100})
  b = _bar(kick={0: 60, 8: 60})
  out = lib.mix_rhythm(a, b, weight=0.5, threshold=0.5)["channels"]["kick"]
  assert out[0] == 80                                       # both: 0.5*100 + 0.5*60
  assert out[4] == 100                                      # a only: renormalised over the bars that have a hit
  assert out[8] == 60                                       # b only


def test_velocity_mean_uses_the_weight_and_rounds_half_up_not_to_even():
  a = _bar(kick={0: 101})
  b = _bar(kick={0: 100})
  assert lib.mix_rhythm(a, b, weight=0.5)["channels"]["kick"][0] == 101     # 100.5 -> 101 (banker's would give 100)
  a2 = _bar(kick={0: 3})
  b2 = _bar(kick={0: 4})
  assert lib.mix_rhythm(a2, b2, weight=0.5)["channels"]["kick"][0] == 4     # 3.5 -> 4
  assert lib.mix_rhythm(a2, b2, weight=0.75, threshold=0.5)["channels"]["kick"][0] == 3   # 3.25 -> 3


def test_a_plain_true_counts_as_90_in_a_mixed_mean_and_stays_plain_only_when_all_are_plain():
  a = _bar(kick={0: True, 4: True})
  b = _bar(kick={0: 110})
  out = lib.mix_rhythm(a, b, weight=0.5)["channels"]["kick"]
  assert out[0] == 100                                      # 0.5*90 + 0.5*110
  assert out[4] is True                                     # only a's plain true contributes -> stays plain


def test_velocity_is_clamped_to_1_127_and_an_int():
  a = _bar(kick={0: 1})
  b = _bar(kick={0: 1})
  out = lib.mix_rhythm(a, b, weight=0.37)["channels"]["kick"][0]
  assert out == 1 and isinstance(out, int) and not isinstance(out, bool)


# ---- ghost notes -----------------------------------------------------------------------------------------

def test_ghost_off_by_default_fails_threshold_steps_are_rests():
  a = _bar(kick={0: True})
  b = _bar(kick={8: True})
  out = lib.mix_rhythm(a, b, weight=0.5, threshold=0.6)["channels"]["kick"]
  assert _hits(out) == {}


def test_ghost_places_a_velocity_36_hit_where_v_is_at_least_half_the_threshold():
  a = _bar(kick={0: True})
  b = _bar(kick={8: True})
  out = lib.mix_rhythm(a, b, weight=0.5, threshold=0.6, ghost=True)["channels"]["kick"]
  assert _hits(out) == {0: 36, 8: 36}                       # v = 0.5 >= 0.3
  assert lib._RHYTHM_GHOST_VELOCITY == 36


def test_ghost_edge_is_inclusive_and_a_step_below_half_threshold_stays_a_rest():
  a = _bar(kick={0: True})
  b = _bar(kick={8: True})
  edge = lib.mix_rhythm(a, b, weight=0.3, threshold=0.6, ghost=True)["channels"]["kick"]
  assert edge[0] == 36                                      # a-only v = 0.3 >= 0.6 / 2: a ghost
  assert edge[8] is True                                    # b-only v = 0.7 >= 0.6: a real (plain) hit, not a ghost
  below = lib.mix_rhythm(a, b, weight=0.2, threshold=0.6, ghost=True)["channels"]["kick"]
  assert 0 not in _hits(below)                              # v = 0.2 < 0.3
  assert below[8] is True


def test_ghost_never_overrides_a_real_hit_and_never_fills_an_empty_step():
  a = _bar(kick={0: 100})
  b = _bar(kick={0: 100})
  out = lib.mix_rhythm(a, b, weight=0.5, threshold=0.6, ghost=True)["channels"]["kick"]
  assert out[0] == 100                                      # v = 1 >= 0.6: a real hit, not a ghost
  assert _hits(out) == {0: 100}                             # empty steps (v = 0) stay rests


def test_ghost_with_threshold_zero_adds_nothing():
  a = _bar(kick={0: True})
  b = _bar(kick={8: True})
  with_ghost = lib.mix_rhythm(a, b, weight=0.5, threshold=0, ghost=True)
  assert with_ghost == lib.mix_rhythm(a, b, weight=0.5, threshold=0, ghost=False)


# ---- channel union ---------------------------------------------------------------------------------------

def test_channels_are_the_union_in_first_seen_order_a_then_new_ones_of_b():
  a = _bar(snare={4: True}, kick={0: True})
  b = _bar(hihat={2: True}, kick={0: True}, snare={4: True})
  out = lib.mix_rhythm(a, b)
  assert list(out["channels"]) == ["snare", "kick", "hihat"]


def test_a_channel_missing_from_one_bar_counts_as_all_rest():
  a = _bar(kick={0: True})
  b = _bar(kick={0: True}, hihat={2: True, 6: True})
  out = lib.mix_rhythm(a, b, weight=0.5, threshold=0.5)["channels"]
  assert set(_hits(out["hihat"])) == {2, 6}
  assert len(out["hihat"]) == 16
  strict = lib.mix_rhythm(a, b, weight=0.5, threshold=0.6)["channels"]
  assert _hits(strict["hihat"]) == {}
  assert list(strict) == ["kick", "hihat"]                  # the channel is still there, all rests


def test_a_channel_missing_from_a_at_weight_one_is_present_and_empty():
  a = _bar(kick={0: True})
  b = _bar(kick={0: True}, hihat={2: True})
  out = lib.mix_rhythm(a, b, weight=1)["channels"]
  assert out["hihat"] == [False] * 16


# ---- tempo and swing -------------------------------------------------------------------------------------

def test_tempo_and_swing_are_the_weighted_mean_rounded_half_up_to_an_int():
  a = _rock(); a["tempo_bpm"] = 100; a["swing_pct"] = 10
  b = _synco(); b["tempo_bpm"] = 121; b["swing_pct"] = 25
  out = lib.mix_rhythm(a, b, weight=0.5)
  assert out["tempo_bpm"] == 111                            # 110.5 -> 111
  assert out["swing_pct"] == 18                             # 17.5 -> 18
  assert isinstance(out["tempo_bpm"], int) and isinstance(out["swing_pct"], int)
  out = lib.mix_rhythm(a, b, weight=0.25)
  assert out["tempo_bpm"] == 116                            # 0.25*100 + 0.75*121 = 115.75 -> 116


def test_tempo_ends_are_exact_and_a_tempo_never_drops_below_one():
  a = _rock(); a["tempo_bpm"] = 60
  b = _synco(); b["tempo_bpm"] = 140
  assert lib.mix_rhythm(a, b, weight=1)["tempo_bpm"] == 60
  assert lib.mix_rhythm(a, b, weight=0)["tempo_bpm"] == 140
  a["tempo_bpm"] = 1; b["tempo_bpm"] = 1
  assert lib.mix_rhythm(a, b, weight=0.4)["tempo_bpm"] == 1


def test_other_top_level_fields_are_a():
  a = _rock(); a["note"] = "kept"
  b = _synco(); b["note"] = "dropped"
  out = lib.mix_rhythm(a, b, weight=0.5)
  assert out["time_signature"] == "4/4" and out["steps"] == 16 and out["group_size"] == 4
  assert out["note"] == "kept"


def test_missing_swing_pct_counts_as_zero():
  a = _rock(); del a["swing_pct"]
  b = _synco(); b["swing_pct"] = 20
  assert lib.mix_rhythm(a, b, weight=0.5)["swing_pct"] == 10


# ---- other grids -----------------------------------------------------------------------------------------

def test_any_matching_grid_is_allowed_not_only_16_steps():
  a = {"time_signature": "3/4", "steps": 12, "group_size": 4, "swing_pct": 0, "tempo_bpm": 90,
       "channels": {"kick": [i in (0, 6) for i in range(12)]}}
  b = {"time_signature": "3/4", "steps": 12, "group_size": 4, "swing_pct": 0, "tempo_bpm": 90,
       "channels": {"kick": [i in (0, 8) for i in range(12)]}}
  out = lib.mix_rhythm(a, b, weight=0.5, threshold=0.6)
  assert out["steps"] == 12 and set(_hits(out["channels"]["kick"])) == {0}
  assert len(out["channels"]["kick"]) == 12


# ---- every ValueError names mix_rhythm -------------------------------------------------------------------

def _err(*args, **kwargs):
  with pytest.raises(ValueError) as exc:
    lib.mix_rhythm(*args, **kwargs)
  assert "mix_rhythm" in str(exc.value)
  return str(exc.value)


@pytest.mark.parametrize("bad", [True, False, "0.5", None, -0.01, 1.01, float("nan"), [0.5]])
def test_weight_must_be_a_number_0_to_1_and_a_bool_is_refused(bad):
  assert "weight" in _err(_rock(), _synco(), weight=bad)


@pytest.mark.parametrize("bad", [True, "0.5", None, -0.01, 1.01, float("nan")])
def test_threshold_must_be_a_number_0_to_1(bad):
  assert "threshold" in _err(_rock(), _synco(), threshold=bad)


@pytest.mark.parametrize("bad", [1, 0, "yes", None])
def test_ghost_must_be_a_bool(bad):
  assert "ghost" in _err(_rock(), _synco(), ghost=bad)


def test_the_ends_of_the_ranges_are_allowed():
  for w in (0, 1, 0.0, 1.0):
    for t in (0, 1, 0.0, 1.0):
      lib.mix_rhythm(_rock(), _synco(), weight=w, threshold=t)


def test_a_and_b_must_be_dicts():
  assert "a" in _err([], _synco())
  assert "b" in _err(_rock(), "bar_006")


@pytest.mark.parametrize("field", ["time_signature", "steps", "group_size", "channels", "tempo_bpm"])
def test_a_missing_required_field_is_named(field):
  a = _rock(); del a[field]
  assert field in _err(a, _synco())
  b = _synco(); del b[field]
  assert field in _err(_rock(), b)


def test_mismatched_time_signature_names_the_field_and_both_values():
  b = _synco(); b["time_signature"] = "3/4"
  msg = _err(_rock(), b)
  assert "time_signature" in msg and "4/4" in msg and "3/4" in msg


def test_mismatched_steps_names_steps():
  b = _synco(); b["steps"] = 12
  b["channels"] = {k: v[:12] for k, v in b["channels"].items()}
  msg = _err(_rock(), b)
  assert "steps" in msg and "16" in msg and "12" in msg


def test_mismatched_group_size_names_group_size():
  b = _synco(); b["group_size"] = 2
  assert "group_size" in _err(_rock(), b)


def test_the_first_mismatch_is_reported_in_field_order():
  b = _synco(); b["time_signature"] = "3/4"; b["steps"] = 12; b["group_size"] = 3
  assert "time_signature" in _err(_rock(), b)


def test_an_unknown_channel_name_is_refused_naming_it():
  a = _rock(); a["channels"]["cowbell"] = [False] * 16
  assert "cowbell" in _err(a, _synco())
  b = _synco(); b["channels"]["cowbell"] = [False] * 16
  assert "cowbell" in _err(_rock(), b)


def test_a_channel_of_the_wrong_length_is_refused_naming_the_channel():
  a = _rock(); a["channels"]["kick"] = [True] * 15
  assert "kick" in _err(a, _synco())


def test_an_invalid_step_value_is_refused_naming_channel_and_index():
  a = _rock(); a["channels"]["snare"][5] = 200
  msg = _err(a, _synco())
  assert "snare" in msg and "5" in msg


def test_channels_must_be_a_dict():
  a = _rock(); a["channels"] = [1]
  assert "channels" in _err(a, _synco())


@pytest.mark.parametrize("bad", [True, 0, -5, "100", None])
def test_tempo_must_be_a_positive_number(bad):
  a = _rock(); a["tempo_bpm"] = bad
  assert "tempo_bpm" in _err(a, _synco())


@pytest.mark.parametrize("bad", [True, -1, 101, "5"])
def test_swing_must_be_a_number_0_to_100(bad):
  b = _synco(); b["swing_pct"] = bad
  assert "swing_pct" in _err(_rock(), b)


# ---- purity ----------------------------------------------------------------------------------------------

def test_inputs_are_not_mutated_and_no_list_is_shared_with_the_result():
  a, b = _rock(), _synco()
  a_before, b_before = copy.deepcopy(a), copy.deepcopy(b)
  out = lib.mix_rhythm(a, b, weight=0.5)
  assert a == a_before and b == b_before
  for name, steps in out["channels"].items():
    for src in (a, b):
      assert steps is not src["channels"].get(name)
  out["channels"]["kick"][0] = 7
  assert a == a_before and b == b_before


def test_the_same_inputs_give_the_same_output():
  assert lib.mix_rhythm(_rock(), _synco(), 0.37, 0.4, True) == lib.mix_rhythm(_rock(), _synco(), 0.37, 0.4, True)


def test_mixing_a_bar_with_itself_is_itself_at_any_weight():
  for w in (0, 0.25, 0.5, 0.8, 1):
    assert lib.mix_rhythm(_rock(), _rock(), weight=w, threshold=1)["channels"] == _rock()["channels"]


# ---- property: raising the weight of a never removes a hit only a has ------------------------------------

def test_raising_weight_never_removes_a_hit_only_a_has_and_never_adds_one_only_b_has():
  a = _bar(kick={0: True, 3: 100, 7: True}, snare={4: True})
  b = _bar(kick={8: True, 3: 80}, snare={12: True}, hihat={2: True})
  for threshold in (0, 0.1, 0.25, 0.5, 0.75, 1):
    prev_a_only = None
    prev_b_only = None
    for k in range(21):
      w = k / 20
      out = lib.mix_rhythm(a, b, weight=w, threshold=threshold)["channels"]
      a_only = {(n, i) for n, ch in out.items() for i in _hits(ch)
                if _hits(a["channels"].get(n, [False] * 16)).get(i) is not None
                and _hits(b["channels"].get(n, [False] * 16)).get(i) is None}
      b_only = {(n, i) for n, ch in out.items() for i in _hits(ch)
                if _hits(b["channels"].get(n, [False] * 16)).get(i) is not None
                and _hits(a["channels"].get(n, [False] * 16)).get(i) is None}
      if prev_a_only is not None:
        assert prev_a_only <= a_only, (threshold, w)
        assert b_only <= prev_b_only, (threshold, w)
      prev_a_only, prev_b_only = a_only, b_only


def test_the_result_renders_through_rhythm_bars_to_stream():
  out = lib.mix_rhythm(_rock(), _synco(), weight=0.5)
  stream = lib.rhythm_bars_to_stream([out])
  assert stream is not None


# ---- gaps found by the mutants ---------------------------------------------------------------------------

def test_a_fractional_tempo_that_rounds_to_zero_is_floored_at_one():
  a = _rock(); a["tempo_bpm"] = 0.4
  b = _synco(); b["tempo_bpm"] = 0.4
  assert lib.mix_rhythm(a, b, weight=0.5)["tempo_bpm"] == 1


def test_a_nested_top_level_field_is_copied_not_shared():
  a = _rock(); a["meta"] = {"tags": ["x"]}
  out = lib.mix_rhythm(a, _synco())
  out["meta"]["tags"].append("y")
  assert a["meta"] == {"tags": ["x"]}


def test_zero_steps_is_refused_naming_steps():
  a = {"time_signature": "4/4", "steps": 0, "group_size": 4, "tempo_bpm": 100, "channels": {}}
  assert "steps" in _err(a, copy.deepcopy(a))


def test_a_non_dict_input_says_it_needs_a_rhythm_data_dict():
  assert "rhythm-data dict" in _err("bar_005", _synco())
  assert "rhythm-data dict" in _err(_rock(), ["kick"])
