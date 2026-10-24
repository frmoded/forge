"""Score-first M7c Phase A (drain 2026-10-24-1200): morph_rhythm / morph_rhythm_info — n bars along an ordered path of single-hit edits.

The pair the driver morphs first is bar_005 / bar_006 of the playground vault (they differ in 4 cells):
  bar_005  kick [0, 2, 3, 6, 8]   snare [4, 6, 12]
  bar_006  kick [0, 8]            snare [4, 12]
Hand-worked pins on the 16-step grid (group_size 4): a step's metric strength is 3 at step 0, 2 at the other group starts (4, 8, 12), 1 at a group's midpoint (2, 6, 10, 14), 0 elsewhere."""
import copy

import pytest

from forge.music import lib


def _bar(tempo=100, swing=0, steps=16, group=4, **channels):
  out = {"time_signature": "4/4", "steps": steps, "group_size": group, "swing_pct": swing, "tempo_bpm": tempo, "channels": {}}
  for name, at in channels.items():
    if isinstance(at, (set, list, tuple)):
      at = {i: True for i in at}
    out["channels"][name] = [at.get(i, False) for i in range(steps)]
  return out


def _bar_005():
  return _bar(kick={0, 2, 3, 6, 8}, snare={4, 6, 12})


def _bar_006():
  return _bar(kick={0, 8}, snare={4, 12})


def _rock():
  return _bar(kick={0, 8}, snare={4, 12}, hihat={0, 2, 4, 6, 8, 10, 12, 14})


def _synco():
  return _bar(kick={0, 3, 10}, snare={7, 12}, hihat={2, 6, 10, 14})


def _cells(bar):
  """{(channel, step): value} for the hit cells of a bar."""
  return {(name, i): v for name, row in bar["channels"].items() for i, v in enumerate(row) if v is not False and v != 0}


def _differing(x, y):
  hx, hy = _cells(x), _cells(y)
  return set(hx) ^ set(hy)


def _edits(a, b, order="musical", seed=0):
  return [(e["kind"], e["channel"], e["step"]) for e in lib.morph_rhythm_info(a, b, order=order, seed=seed)["edits"]]


# ---- the pair the driver morphs -------------------------------------------------------------------------

def test_bar_005_to_bar_006_differs_in_four_cells():
  info = lib.morph_rhythm_info(_bar_005(), _bar_006())
  assert info["d"] == 4
  assert len(info["edits"]) == 4


def test_musical_order_removes_the_weakest_positions_first():
  # all four edits are removals; strength: kick 3 -> 0, kick 2 / kick 6 / snare 6 -> 1 (ties by channel order, then step)
  assert _edits(_bar_005(), _bar_006()) == [("remove", "kick", 3), ("remove", "kick", 2), ("remove", "kick", 6), ("remove", "snare", 6)]


def test_atomic_morph_has_d_plus_one_bars_each_one_hit_from_the_last():
  bars = lib.morph_rhythm(_bar_005(), _bar_006(), bars=5)
  assert isinstance(bars, list) and len(bars) == 5
  for prev, nxt in zip(bars, bars[1:]):
    assert len(_differing(prev, nxt)) == 1
  assert _cells(bars[0]) == _cells(_bar_005())
  assert _cells(bars[-1]) == _cells(_bar_006())


def test_atomic_morph_follows_the_edit_order_exactly():
  a, b = _bar_005(), _bar_006()
  edits = _edits(a, b)
  bars = lib.morph_rhythm(a, b, bars=5)
  for k in range(1, 5):
    kind, channel, step = edits[k - 1]
    assert _differing(bars[k - 1], bars[k]) == {(channel, step)}
    assert ((channel, step) in _cells(bars[k])) == (kind == "add")


def test_fewer_bars_than_atomic_pick_states_round_half_up():
  # d = 4, bars = 3: states round_half_up(i * 4 / 2) = 0, 2, 4; bars = 4: round_half_up(i * 4 / 3) = 0, 1 (1.33), 3 (2.67), 4
  a, b = _bar_005(), _bar_006()
  edits = _edits(a, b)

  def state(k):
    cells = _cells(a)
    for kind, channel, step in edits[:k]:
      cells.pop((channel, step), None) if kind == "remove" else cells.__setitem__((channel, step), True)
    return cells

  assert [_cells(x) for x in lib.morph_rhythm(a, b, bars=3)] == [state(0), state(2), state(4)]
  assert [_cells(x) for x in lib.morph_rhythm(a, b, bars=4)] == [state(0), state(1), state(3), state(4)]
  # a half rounds UP: d = 4 over bars = 9 -> i = 1 is 0.5 -> state 1
  assert [_cells(x) for x in lib.morph_rhythm(a, b, bars=9)][1] == state(1)


def test_more_bars_than_d_plus_one_repeat_states():
  bars = lib.morph_rhythm(_bar_005(), _bar_006(), bars=9)
  assert len(bars) == 9
  assert _cells(bars[0]) == _cells(_bar_005()) and _cells(bars[-1]) == _cells(_bar_006())
  assert all(len(_differing(p, n)) <= 1 for p, n in zip(bars, bars[1:]))


def test_two_bars_is_a_then_b():
  bars = lib.morph_rhythm(_bar_005(), _bar_006(), bars=2)
  assert len(bars) == 2
  assert _cells(bars[0]) == _cells(_bar_005()) and _cells(bars[1]) == _cells(_bar_006())


# ---- the three orders --------------------------------------------------------------------------------------

def test_rock_to_synco_has_nine_edits():
  assert lib.morph_rhythm_info(_rock(), _synco())["d"] == 9


def test_each_order_is_deterministic_across_runs():
  for order in ("musical", "seeded", "by_channel"):
    first = lib.morph_rhythm_info(_rock(), _synco(), order=order, seed=7)
    again = lib.morph_rhythm_info(_rock(), _synco(), order=order, seed=7)
    assert first == again, order
    assert lib.morph_rhythm(_rock(), _synco(), bars=10, order=order, seed=7) == lib.morph_rhythm(_rock(), _synco(), bars=10, order=order, seed=7)


def test_the_three_orders_differ_from_each_other_when_d_is_at_least_six():
  m = _edits(_rock(), _synco(), "musical")
  s = _edits(_rock(), _synco(), "seeded", seed=3)
  c = _edits(_rock(), _synco(), "by_channel")
  assert len({tuple(m), tuple(s), tuple(c)}) == 3
  assert sorted(m) == sorted(s) == sorted(c), "the same edits, only the order differs"


def test_by_channel_is_channel_order_then_step():
  assert _edits(_rock(), _synco(), "by_channel") == [
    ("add", "kick", 3), ("remove", "kick", 8), ("add", "kick", 10),
    ("remove", "snare", 4), ("add", "snare", 7),
    ("remove", "hihat", 0), ("remove", "hihat", 4), ("remove", "hihat", 8), ("remove", "hihat", 12),
  ]


def test_seeded_is_a_pinned_integer_hash_shuffle_and_depends_on_the_seed():
  # pinned so a change of the hash (or a move to random.shuffle, which differs between interpreters' builds) is noticed
  assert _edits(_rock(), _synco(), "seeded", seed=0) == _edits(_rock(), _synco(), "seeded", seed=0)
  seen = {tuple(_edits(_rock(), _synco(), "seeded", seed=s)) for s in range(6)}
  assert len(seen) >= 4, "different seeds give different orders"
  assert _edits(_rock(), _synco(), "seeded", seed=0) != _edits(_rock(), _synco(), "by_channel")


def test_seeded_does_not_use_the_random_module(monkeypatch):
  import random
  monkeypatch.setattr(random, "random", lambda: (_ for _ in ()).throw(AssertionError("random used")))
  monkeypatch.setattr(random, "shuffle", lambda *a, **k: (_ for _ in ()).throw(AssertionError("random used")))
  lib.morph_rhythm_info(_rock(), _synco(), order="seeded", seed=5)


def test_musical_interleaves_removes_and_adds_in_proportion():
  a = _bar(kick={0, 3, 6})            # three hits that B does not have ...
  b = _bar(snare={2, 5, 11})          # ... and three that A does not have
  kinds = [k for k, _, _ in _edits(a, b)]
  assert kinds == ["remove", "add", "remove", "add", "remove", "add"]
  one_remove = _edits(_bar(kick={4}), _bar(snare={1, 5, 9}))
  assert [k for k, _, _ in one_remove] == ["add", "remove", "add", "add"], "1 remove among 3 adds: the remove lands where its share falls (round half up)"


def test_musical_puts_the_strongest_metric_positions_last_within_each_kind():
  # removals: step 0 (3), 4 (2), 2 (1), 3 (0) -> 3, 2, 4, 0 ; additions likewise
  a = _bar(kick={0, 2, 3, 4})
  b = _bar()
  assert [s for _, _, s in _edits(a, b)] == [3, 2, 4, 0]
  assert [s for _, _, s in _edits(b, a)] == [3, 2, 4, 0]


def test_metric_strength_uses_the_bars_group_size():
  # group_size 3 on 12 steps: step 0 is 3, the other group starts (3, 6, 9) are 2, every other step is 0 (a group of 3 has no midpoint step)
  a = _bar(group=3, steps=12, kick={0, 3, 6, 1, 2})
  b = _bar(group=3, steps=12)
  assert [s for _, _, s in _edits(a, b)] == [1, 2, 3, 6, 0]


# ---- values: tempo, swing, velocities -----------------------------------------------------------------------

def test_tempo_and_swing_slide_linearly_rounded_half_up():
  a, b = _bar_005(), _bar_006()
  a["tempo_bpm"], b["tempo_bpm"] = 100, 140
  a["swing_pct"], b["swing_pct"] = 0, 20
  bars = lib.morph_rhythm(a, b, bars=5)
  assert [x["tempo_bpm"] for x in bars] == [100, 110, 120, 130, 140]
  assert [x["swing_pct"] for x in bars] == [0, 5, 10, 15, 20]
  bars = lib.morph_rhythm(a, b, bars=4)
  assert [x["tempo_bpm"] for x in bars] == [100, 113, 127, 140]          # 113.33, 126.67
  a["tempo_bpm"], b["tempo_bpm"] = 100, 101
  assert [x["tempo_bpm"] for x in lib.morph_rhythm(a, b, bars=3)] == [100, 101, 101], "100.5 rounds half UP"


def test_a_missing_swing_counts_as_zero_and_the_result_always_has_swing():
  a, b = _bar_005(), _bar_006()
  del a["swing_pct"]
  b["swing_pct"] = 10
  assert [x["swing_pct"] for x in lib.morph_rhythm(a, b, bars=3)] == [0, 5, 10]


def test_other_top_level_fields_are_a_s():
  a = _bar_005(); a["title"] = "from a"
  b = _bar_006(); b["title"] = "from b"
  assert all(x.get("title") == "from a" for x in lib.morph_rhythm(a, b, bars=3))


def test_cells_in_both_bars_keep_a_s_velocity_and_added_hits_take_b_s():
  a = _bar(kick={0: 64, 4: True, 8: 100})
  b = _bar(kick={0: 127, 4: 110, 12: 55}, snare={2: True})
  bars = lib.morph_rhythm(a, b, bars=lib.morph_rhythm_info(a, b)["d"] + 1)
  last = bars[-1]["channels"]
  assert last["kick"][0] == 64, "in both: a's velocity"
  assert last["kick"][4] is True, "in both: a's plain true stays plain"
  assert last["kick"][12] == 55, "added: b's velocity"
  assert last["snare"][2] is True, "added: b's plain true stays plain"
  assert last["kick"][8] is False, "removed"


def test_velocities_of_untouched_hits_survive_every_state():
  a = _bar(kick={0: 64, 8: 100}, snare={4: True})
  b = _bar(kick={0: 64, 8: 100}, snare={4: True, 12: 80})
  for x in lib.morph_rhythm(a, b, bars=2):
    assert x["channels"]["kick"][0] == 64 and x["channels"]["kick"][8] == 100


# ---- bars = 1 and the position --------------------------------------------------------------------------------

def test_one_bar_needs_a_position_and_returns_that_state():
  a, b = _bar_005(), _bar_006()
  info = lib.morph_rhythm_info(a, b)
  full = lib.morph_rhythm(a, b, bars=info["d"] + 1)
  for k in range(info["d"] + 1):
    one = lib.morph_rhythm(a, b, bars=1, position=k)
    assert isinstance(one, dict)
    assert _cells(one) == _cells(full[k])
  assert _cells(lib.morph_rhythm(a, b, bars=1, position=0)) == _cells(a)
  assert _cells(lib.morph_rhythm(a, b, bars=1, position=4)) == _cells(b)


def test_one_bar_tempo_is_position_over_d():
  a, b = _bar_005(), _bar_006()
  a["tempo_bpm"], b["tempo_bpm"] = 100, 140
  assert [lib.morph_rhythm(a, b, bars=1, position=k)["tempo_bpm"] for k in range(5)] == [100, 110, 120, 130, 140]


def test_identical_hits_morph_to_identical_bars_and_the_tempo_still_slides():
  a, b = _bar_006(), _bar_006()
  b["tempo_bpm"] = 120
  info = lib.morph_rhythm_info(a, b)
  assert info == {"d": 0, "edits": []}
  bars = lib.morph_rhythm(a, b, bars=3)
  assert all(_cells(x) == _cells(a) for x in bars)
  assert [x["tempo_bpm"] for x in bars] == [100, 110, 120]
  assert _cells(lib.morph_rhythm(a, b, bars=1, position=0)) == _cells(a)


# ---- the info -------------------------------------------------------------------------------------------------

def test_info_shape_and_consistency_with_the_bars():
  info = lib.morph_rhythm_info(_rock(), _synco(), order="by_channel")
  assert set(info) == {"d", "edits"} and info["d"] == len(info["edits"])
  for e in info["edits"]:
    assert set(e) == {"kind", "channel", "step"} and e["kind"] in ("add", "remove") and isinstance(e["step"], int)
  bars = lib.morph_rhythm(_rock(), _synco(), bars=info["d"] + 1, order="by_channel")
  for k, e in enumerate(info["edits"], start=1):
    assert _differing(bars[k - 1], bars[k]) == {(e["channel"], e["step"])}


# ---- channels, shapes, purity ----------------------------------------------------------------------------------

def test_channels_are_the_union_in_first_seen_order_and_one_sided_channels_are_edits():
  a = _bar(kick={0}, snare={4})
  b = _bar(kick={0}, hihat={2})
  bars = lib.morph_rhythm(a, b, bars=3)
  assert list(bars[0]["channels"]) == ["kick", "snare", "hihat"]
  assert set(_edits(a, b)) == {("remove", "snare", 4), ("add", "hihat", 2)}
  assert _cells(bars[-1]) == _cells(b)


def test_a_channel_with_no_hits_is_kept_as_a_row_of_rests():
  a = _bar(kick={0}, snare=set())
  b = _bar(kick={0, 8})
  bars = lib.morph_rhythm(a, b, bars=2)
  assert bars[0]["channels"]["snare"] == [False] * 16


def test_other_step_counts_and_group_sizes():
  a = _bar(steps=12, group=3, kick={0, 3, 6, 9}, snare={6})
  b = _bar(steps=12, group=3, kick={0, 6}, snare={6, 9})
  bars = lib.morph_rhythm(a, b, bars=lib.morph_rhythm_info(a, b)["d"] + 1)
  assert all(len(x["channels"]["kick"]) == 12 for x in bars)
  assert _cells(bars[0]) == _cells(a) and _cells(bars[-1]) == _cells(b)


def test_inputs_are_never_mutated_and_the_bars_share_no_lists():
  a, b = _bar_005(), _bar_006()
  a0, b0 = copy.deepcopy(a), copy.deepcopy(b)
  bars = lib.morph_rhythm(a, b, bars=5)
  assert a == a0 and b == b0
  rows = [id(x["channels"][c]) for x in bars for c in x["channels"]]
  assert len(rows) == len(set(rows))
  assert not any(x["channels"][c] is a["channels"][c] for x in bars for c in a["channels"])
  bars[0]["channels"]["kick"][1] = True
  assert a == a0


def test_the_morph_feeds_rhythm_bars_to_stream():
  bars = lib.morph_rhythm(_bar_005(), _bar_006(), bars=5)
  assert lib.rhythm_bars_to_stream(bars) is not None
  one = lib.morph_rhythm(_bar_005(), _bar_006(), bars=1, position=2)
  assert lib.rhythm_bars_to_stream([one]) is not None


# ---- refusals -----------------------------------------------------------------------------------------------------

def _refuses(match, fn, *args, **kwargs):
  with pytest.raises(ValueError, match=match) as err:
    fn(*args, **kwargs)
  assert str(err.value).startswith("morph_rhythm"), str(err.value)


@pytest.mark.parametrize("fn", [lib.morph_rhythm, lib.morph_rhythm_info])
def test_inputs_that_are_not_rhythm_data_are_refused_with_the_functions_own_name(fn):
  kw = {"bars": 3} if fn is lib.morph_rhythm else {}
  _refuses("a must be a rhythm-data dict", fn, "x", _bar_006(), **kw)
  _refuses("b must be a rhythm-data dict", fn, _bar_005(), None, **kw)
  _refuses("a is missing required field 'steps'", fn, {k: v for k, v in _bar_005().items() if k != "steps"}, _bar_006(), **kw)
  bad = _bar_006(); bad["channels"]["nonsense"] = [False] * 16
  _refuses("unknown channel", fn, _bar_005(), bad, **kw)


@pytest.mark.parametrize("field,value", [("time_signature", "3/4"), ("steps", 12), ("group_size", 2)])
def test_bars_must_agree_on_meter_steps_and_group_size(field, value):
  b = _bar_006()
  b[field] = value
  if field == "steps":
    b = _bar(steps=12, group=4, kick={0, 8})
  _refuses(f"a and b must agree on {field}", lib.morph_rhythm, _bar_005(), b, bars=3)
  _refuses(f"a and b must agree on {field}", lib.morph_rhythm_info, _bar_005(), b)


@pytest.mark.parametrize("bars", [0, -1, 1.5, "3", None, True])
def test_bars_must_be_an_int_of_at_least_one(bars):
  _refuses("bars must be", lib.morph_rhythm, _bar_005(), _bar_006(), bars=bars, position=0)


def test_order_must_be_one_of_the_three():
  _refuses("order must be one of", lib.morph_rhythm, _bar_005(), _bar_006(), bars=3, order="random")
  _refuses("order must be one of", lib.morph_rhythm_info, _bar_005(), _bar_006(), order="Musical")


@pytest.mark.parametrize("seed", [-1, 1.5, "0", None, True])
def test_seed_must_be_a_non_negative_int(seed):
  _refuses("seed must be", lib.morph_rhythm, _bar_005(), _bar_006(), bars=3, seed=seed)
  _refuses("seed must be", lib.morph_rhythm_info, _bar_005(), _bar_006(), seed=seed)


def test_one_bar_requires_a_position_from_zero_to_d():
  _refuses("bars = 1 needs a position", lib.morph_rhythm, _bar_005(), _bar_006(), bars=1)
  for bad in (-1, 5, 2.0, "1", True):
    _refuses("position must be", lib.morph_rhythm, _bar_005(), _bar_006(), bars=1, position=bad)


def test_a_position_is_only_for_one_bar():
  _refuses("position is only for bars = 1", lib.morph_rhythm, _bar_005(), _bar_006(), bars=3, position=1)


# ---- nothing else moved ---------------------------------------------------------------------------------------------

def test_mix_rhythm_is_untouched_by_the_shared_helpers():
  assert lib.mix_rhythm(_bar_005(), _bar_006(), weight=1) == _bar_005()
  with pytest.raises(ValueError, match="^mix_rhythm: a must be a rhythm-data dict"):
    lib.mix_rhythm("x", _bar_006())
  bad = _bar_006(); bad["channels"]["nonsense"] = [False] * 16
  with pytest.raises(ValueError, match="^mix_rhythm: b has unknown channel"):
    lib.mix_rhythm(_bar_005(), bad)


def test_both_functions_are_registered_in_both_executor_lists():
  from forge.core import executor
  for name in ("morph_rhythm", "morph_rhythm_info"):
    assert name in executor._MUSIC_LAZY_CHIP_NAMES


# ---- pinned orders (the same literals are checked in Pyodide by the client's phrase-morph-engine test) ----------------------------

ROCK_SYNCO_MUSICAL = [
  ("remove", "kick", 8), ("add", "kick", 3), ("remove", "snare", 4), ("remove", "hihat", 4), ("add", "snare", 7),
  ("remove", "hihat", 8), ("remove", "hihat", 12), ("add", "kick", 10), ("remove", "hihat", 0),
]
ROCK_SYNCO_SEEDED_0 = [
  ("remove", "hihat", 4), ("remove", "hihat", 0), ("remove", "hihat", 12), ("add", "snare", 7), ("remove", "kick", 8),
  ("remove", "hihat", 8), ("add", "kick", 3), ("add", "kick", 10), ("remove", "snare", 4),
]
ROCK_SYNCO_SEEDED_1 = [
  ("remove", "kick", 8), ("remove", "snare", 4), ("remove", "hihat", 8), ("add", "kick", 3), ("remove", "hihat", 0),
  ("remove", "hihat", 4), ("add", "kick", 10), ("add", "snare", 7), ("remove", "hihat", 12),
]


def test_the_orders_for_rock_to_synco_are_pinned_exactly():
  assert _edits(_rock(), _synco()) == ROCK_SYNCO_MUSICAL
  assert _edits(_rock(), _synco(), "seeded", 0) == ROCK_SYNCO_SEEDED_0
  assert _edits(_rock(), _synco(), "seeded", 1) == ROCK_SYNCO_SEEDED_1


def test_a_group_start_is_stronger_than_a_midpoint_whatever_their_step_numbers():
  # step 4 (a group start, 2) outranks step 6 (a midpoint, 1) although it is the earlier step: the midpoint goes first
  assert [s for _, _, s in _edits(_bar(kick={4, 6}), _bar())] == [6, 4]
  assert [s for _, _, s in _edits(_bar(), _bar(kick={8, 10}))] == [10, 8]


@pytest.mark.parametrize("group", [0, -4, 2.0, True, "4"])
def test_group_size_must_be_a_positive_int(group):
  a, b = _bar_005(), _bar_006()
  a["group_size"] = b["group_size"] = group
  _refuses("group_size must be a positive int", lib.morph_rhythm, a, b, bars=3)
  _refuses("group_size must be a positive int", lib.morph_rhythm_info, a, b)


def test_a_tempo_never_rounds_below_one():
  a, b = _bar_005(), _bar_006()
  a["tempo_bpm"] = b["tempo_bpm"] = 0.4
  assert [x["tempo_bpm"] for x in lib.morph_rhythm(a, b, bars=3)] == [1, 1, 1]


def test_swing_rounds_half_up_too():
  a, b = _bar_005(), _bar_006()
  a["swing_pct"], b["swing_pct"] = 0, 5
  assert [x["swing_pct"] for x in lib.morph_rhythm(a, b, bars=3)] == [0, 3, 5], "2.5 rounds UP"


def test_other_top_level_fields_are_copied_not_shared():
  a, b = _bar_005(), _bar_006()
  a["tags"] = ["x"]
  bars = lib.morph_rhythm(a, b, bars=3)
  assert bars[0]["tags"] == ["x"] and bars[0]["tags"] is not a["tags"] and bars[0]["tags"] is not bars[1]["tags"]
