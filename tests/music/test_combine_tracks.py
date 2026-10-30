"""2026-10-29-0820 (score-first M10 slice 1, design 4.10): combine_tracks - merge the bar lists of several tracks, channel by channel, into ONE list of rhythm-data bars.

A track is {"kit": <name>, "channels": [<channel names>], "bars": [<rhythm-data bars>]}: a phrase's bars played on a kit. The kit names the channels the track may use.
  * a track contributes only the channels that are in its kit (a channel of the phrase the kit does not have is dropped, not an error);
  * a channel that two kits both have is a refusal naming the channel and both kits (even when no phrase hits it: the kits conflict);
  * the tracks may have different lengths: the result has as many bars as the longest, and a shorter track's channels are all rest after its last bar (explicit rests);
  * every bar of every track must agree on time_signature, steps, group_size, tempo_bpm and swing_pct with the bar at the same position in the other tracks, else a plain
    refusal naming the field, the bar number and the two kits (v1: same meter, same steps, same tempo);
  * the channels of every result bar are the same set, in the engine's canonical channel order (kick, snare, hihat, bell, claves, conga_high, conga_low), never the order the tracks came in;
  * pure: the inputs are never changed and the result shares no list with them; no randomness; no hit is added, none is lost, velocities are kept.

Hand-worked pin (16 steps, group 4): rock plays 2 bars on {kick, snare, hihat}, latin plays 1 bar on {claves, bell}.
  rock bar 1  kick [0, 8]  snare [4, 12]  hihat [0, 4, 8, 12]      rock bar 2  kick [0]  snare [4]
  latin bar 1 claves [0, 3, 6, 10, 12]  bell [0, 8]  (and a kick [0] that its kit does not have: dropped)
  result: 2 bars; bar 1 = kick, snare, hihat, bell, claves as played; bar 2 = kick [0], snare [4], and hihat, bell, claves all rest.
"""
import copy
import itertools
import random

import pytest

from forge.music import lib

CANONICAL = ["kick", "snare", "hihat", "bell", "claves", "conga_high", "conga_low"]


def _bar(tempo=100, swing=0, steps=16, group=4, ts="4/4", **channels):
  out = {"time_signature": ts, "steps": steps, "group_size": group, "swing_pct": swing, "tempo_bpm": tempo, "channels": {}}
  for name, at in channels.items():
    if isinstance(at, (set, list, tuple)):
      at = {i: True for i in at}
    out["channels"][name] = [at.get(i, False) for i in range(steps)]
  return out


def _track(kit, channels, bars):
  return {"kit": kit, "channels": list(channels), "bars": bars}


def _hits(bar, channel):
  return [i for i, v in enumerate(bar["channels"][channel]) if v is not False and v != 0]


def _rock():
  return _track("rock", ["kick", "snare", "hihat"], [
    _bar(kick={0, 8}, snare={4, 12}, hihat={0, 4, 8, 12}),
    _bar(kick={0}, snare={4}),
  ])


def _latin():
  return _track("latin", ["bell", "claves", "conga_high", "conga_low"], [_bar(claves={0, 3, 6, 10, 12}, bell={0, 8}, kick={0})])


# ---- the hand-worked pin ---------------------------------------------------------------------------------------------------------------------------------------------------------

def test_rock_and_latin_hand_worked_result():
  out = lib.combine_tracks([_rock(), _latin()])
  assert len(out) == 2
  assert list(out[0]["channels"]) == ["kick", "snare", "hihat", "bell", "claves"]
  assert list(out[1]["channels"]) == ["kick", "snare", "hihat", "bell", "claves"]
  assert _hits(out[0], "kick") == [0, 8] and _hits(out[0], "snare") == [4, 12] and _hits(out[0], "hihat") == [0, 4, 8, 12]
  assert _hits(out[0], "bell") == [0, 8] and _hits(out[0], "claves") == [0, 3, 6, 10, 12]
  assert _hits(out[1], "kick") == [0] and _hits(out[1], "snare") == [4]
  for rest in ("hihat", "bell", "claves"):
    assert out[1]["channels"][rest] == [False] * 16, f"bar 2 {rest} is all rest (explicit padding)"
  for bar in out:
    assert (bar["time_signature"], bar["steps"], bar["group_size"], bar["tempo_bpm"], bar["swing_pct"]) == ("4/4", 16, 4, 100, 0)


def test_a_channel_the_kit_does_not_have_is_dropped_not_an_error():
  out = lib.combine_tracks([_latin()])           # the latin phrase also hits a kick; the latin kit has no kick
  assert "kick" not in out[0]["channels"]
  assert list(out[0]["channels"]) == ["bell", "claves"]


def test_velocities_and_plain_hits_are_kept_exactly():
  bar = _bar(kick={0: 112, 8: True}, snare={4: 64})
  out = lib.combine_tracks([_track("rock", ["kick", "snare"], [bar])])
  assert out[0]["channels"]["kick"][0] == 112 and out[0]["channels"]["kick"][8] is True
  assert out[0]["channels"]["snare"][4] == 64


def test_one_track_with_a_full_kit_is_its_own_bars():
  bars = [_bar(kick={0, 8}, snare={4, 12}, hihat={0, 4, 8, 12}), _bar(kick={0}, snare={4}, hihat=set())]      # the same channels in every bar
  assert lib.combine_tracks([_track("rock", ["kick", "snare", "hihat"], bars)]) == bars


def test_a_channel_some_bars_lack_is_an_explicit_rest_in_the_bars_that_lack_it():
  out = lib.combine_tracks([_rock()])        # rock bar 2 has no hihat; the result says so with a row of rests, like every other bar
  assert out[1]["channels"]["hihat"] == [False] * 16


# ---- unequal lengths ---------------------------------------------------------------------------------------------------------------------------------------------------------

def test_the_result_is_as_long_as_the_longest_track_and_a_short_track_rests_after_its_last_bar():
  long_track = _track("rock", ["kick", "snare"], [_bar(kick={0}), _bar(kick={0}), _bar(kick={0}), _bar(kick={0})])
  short_track = _track("latin", ["bell"], [_bar(bell={0, 8})])
  out = lib.combine_tracks([long_track, short_track])
  assert len(out) == 4
  assert _hits(out[0], "bell") == [0, 8]
  for bar in out[1:]:
    assert bar["channels"]["bell"] == [False] * 16
  for bar in out:
    assert _hits(bar, "kick") == [0]


# ---- refusals ----------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_a_channel_two_kits_both_have_is_a_refusal_naming_the_channel_and_both_kits():
  a = _track("rock", ["kick", "snare"], [_bar(kick={0})])
  b = _track("punk", ["snare", "hihat"], [_bar(hihat={0})])          # neither phrase hits the shared snare: the KITS conflict
  with pytest.raises(ValueError) as e:
    lib.combine_tracks([a, b])
  text = str(e.value)
  assert "snare" in text and "rock" in text and "punk" in text and "combine_tracks" in text


def test_the_same_kit_twice_is_the_same_conflict():
  with pytest.raises(ValueError, match="kick"):
    lib.combine_tracks([_rock(), _rock()])


# 2026-10-29-0910 (deliberate): tempo_bpm LEFT this list - a different tempo is no longer a refusal, the arrangement plays at the first track's tempo (see the re-timing tests below). Meter, steps, group size and swing stay refusals.
@pytest.mark.parametrize("field,value", [("time_signature", "3/4"), ("steps", 12), ("group_size", 3), ("swing_pct", 30)])
def test_a_different_meter_steps_or_swing_is_a_plain_refusal_naming_field_bar_and_kits(field, value):
  other = _latin()
  if field == "steps":
    other["bars"] = [_bar(steps=12, group=4, claves={0, 3})]
  else:
    other["bars"][0][field] = value
    if field == "time_signature":
      other["bars"][0][field] = value
  with pytest.raises(ValueError) as e:
    lib.combine_tracks([_rock(), other])
  text = str(e.value)
  assert field in text and "bar 1" in text and "rock" in text and "latin" in text


# 2026-10-29-0910 (deliberate): this test pinned "a tempo that differs in a bar both tracks have is a refusal naming bar 2". The driver decided RE-TIME instead: the second track's bar takes the first track's tempo.
def test_a_tempo_that_differs_in_a_bar_both_tracks_have_is_re_timed_to_the_first_tracks_not_refused():
  a = _track("rock", ["kick"], [_bar(tempo=100, kick={0}), _bar(tempo=90, kick={0})])
  b = _track("latin", ["bell"], [_bar(tempo=100, bell={0}), _bar(tempo=95, bell={0})])
  out = lib.combine_tracks([a, b])
  assert [bar["tempo_bpm"] for bar in out] == [100, 90], "bar 2 plays at rock's 90, not latin's 95"
  assert [bar["tempo_bpm"] for bar in b["bars"]] == [100, 95], "the input is never changed"


def test_a_ritardando_inside_every_track_is_fine_when_the_tracks_agree_bar_by_bar():
  a = _track("rock", ["kick"], [_bar(tempo=100, kick={0}), _bar(tempo=90, kick={0})])
  b = _track("latin", ["bell"], [_bar(tempo=100, bell={0}), _bar(tempo=90, bell={0})])
  out = lib.combine_tracks([a, b])
  assert [bar["tempo_bpm"] for bar in out] == [100, 90]


@pytest.mark.parametrize("bad", [None, [], "tracks", [None], [{}], [{"kit": "", "channels": ["kick"], "bars": [_bar(kick={0})]}],
                                 [{"kit": "rock", "channels": [], "bars": [_bar(kick={0})]}], [{"kit": "rock", "channels": ["kick"], "bars": []}],
                                 [{"kit": "rock", "channels": "kick", "bars": [_bar(kick={0})]}], [{"kit": "rock", "channels": ["triangle"], "bars": [_bar(kick={0})]}]])
def test_malformed_tracks_are_refused_in_a_sentence_that_names_the_function(bad):
  with pytest.raises(ValueError, match="combine_tracks"):
    lib.combine_tracks(bad)


def test_a_bar_with_an_unknown_channel_is_refused_like_every_other_rhythm_function():
  with pytest.raises(ValueError, match="triangle"):
    lib.combine_tracks([_track("rock", ["kick"], [{**_bar(kick={0}), "channels": {"triangle": [False] * 16}}])])


# ---- properties (deterministic: a seeded generator, many cases) -----------------------------------------------------------------------------------------------------------

def _random_tracks(rng):
  vocab = list(CANONICAL)
  rng.shuffle(vocab)
  cut = [0, rng.randint(1, 3), rng.randint(4, 7)]
  groups = [vocab[cut[0]:cut[1]], vocab[cut[1]:cut[2]]] + ([vocab[cut[2]:]] if vocab[cut[2]:] and rng.random() < 0.5 else [])
  tracks = []
  for index, kit_channels in enumerate(groups):
    if not kit_channels:
      continue
    bars = []
    for _ in range(rng.randint(1, 4)):
      played = rng.sample(CANONICAL, rng.randint(1, 4))       # the phrase may hit channels its kit does not have
      bars.append(_bar(**{name: {s: (rng.choice([True, 40, 112])) for s in rng.sample(range(16), rng.randint(0, 6))} for name in played}))
    tracks.append(_track(f"kit{index}", kit_channels, bars))
  return tracks


@pytest.mark.parametrize("seed", range(40))
def test_properties_hold_on_random_tracks(seed):
  rng = random.Random(seed)
  tracks = _random_tracks(rng)
  before = copy.deepcopy(tracks)
  out = lib.combine_tracks(tracks)
  assert tracks == before, "the inputs are never changed"
  assert len(out) == max(len(t["bars"]) for t in tracks), "as long as the longest track"
  # canonical order, the same channel set in every bar
  sets = [list(bar["channels"]) for bar in out]
  assert all(s == sets[0] for s in sets)
  assert sets[0] == [c for c in CANONICAL if c in sets[0]]
  # no hit added, none lost, velocities kept: each (bar, channel) of the result is exactly the owning track's bar, or all rest
  for number, bar in enumerate(out):
    for name, row in bar["channels"].items():
      owner = next(t for t in tracks if name in t["channels"])
      if number < len(owner["bars"]) and name in owner["bars"][number]["channels"]:
        assert row == owner["bars"][number]["channels"][name], (seed, number, name)
      else:
        assert row == [False] * 16, (seed, number, name)
  total_in = sum(1 for t in tracks for b in t["bars"] for n, r in b["channels"].items() if n in t["channels"] for v in r if v is not False and v != 0)
  total_out = sum(1 for b in out for r in b["channels"].values() for v in r if v is not False and v != 0)
  assert total_in == total_out, "hits are conserved"
  # the order the tracks come in does not matter
  for perm in itertools.islice(itertools.permutations(tracks), 6):
    assert lib.combine_tracks(list(perm)) == out
  # no list is shared with the inputs
  for bar in out:
    for row in bar["channels"].values():
      assert not any(row is r for t in tracks for b in t["bars"] for r in b["channels"].values())


def test_the_result_feeds_rhythm_bars_to_stream():
  pytest.importorskip("music21")
  stream = lib.rhythm_bars_to_stream(lib.combine_tracks([_rock(), _latin()]))
  assert stream is not None


# ---- 2026-10-29-0910: tempo re-timing -----------------------------------------------------------------------------------------------------------------------------------------------

def test_every_bar_plays_at_the_first_tracks_tempo_whatever_the_order_the_others_come_in():
  slow = _track("rock", ["kick"], [_bar(tempo=60, kick={0}), _bar(tempo=70, kick={0})])
  fast = _track("latin", ["bell"], [_bar(tempo=180, bell={0}), _bar(tempo=150, bell={0})])
  assert [b["tempo_bpm"] for b in lib.combine_tracks([slow, fast])] == [60, 70]
  assert [b["tempo_bpm"] for b in lib.combine_tracks([fast, slow])] == [180, 150], "the FIRST track decides"


def test_beyond_the_first_tracks_length_a_longer_track_keeps_its_own_tempo():
  short = _track("rock", ["kick"], [_bar(tempo=100, kick={0})])
  long = _track("latin", ["bell"], [_bar(tempo=140, bell={0}), _bar(tempo=130, bell={0}), _bar(tempo=120, bell={0})])
  assert [b["tempo_bpm"] for b in lib.combine_tracks([short, long])] == [100, 130, 120]


def test_the_tempo_is_the_first_tracks_even_when_that_track_is_muted():
  rock = _track("rock", ["kick"], [_bar(tempo=100, kick={0})])
  rock["mute"] = True
  latin = _track("latin", ["bell"], [_bar(tempo=160, bell={0})])
  assert [b["tempo_bpm"] for b in lib.combine_tracks([rock, latin])] == [100]


# ---- 2026-10-29-0910: lineage (combine_tracks_lineage) -----------------------------------------------------------------------------------------------------------------------------

def _named(track, phrase):
  return dict(track, phrase=phrase)


def test_the_bars_do_not_change_because_the_tracks_carry_phrase_names():
  plain = lib.combine_tracks([_rock(), _latin()])
  named = lib.combine_tracks([_named(_rock(), "phrase_001"), _named(_latin(), "phrase_002")])
  assert plain == named


def test_lineage_of_equal_length_tracks_names_the_phrase_and_kit_of_each_channel_group_per_bar():
  a = _named(_track("rock", ["kick", "snare"], [_bar(kick={0}, snare={4}), _bar(kick={0}, snare={4})]), "phrase_001")
  b = _named(_track("latin", ["bell"], [_bar(bell={0}), _bar(bell={2})]), "phrase_002")
  lineage = lib.combine_tracks_lineage([a, b])
  assert [row["bar"] for row in lineage] == [1, 2]
  for position, row in enumerate(lineage, start=1):
    assert row["tempo_bpm"] == 100 and row["retimed_from"] == {}
    assert row["channels"] == {"kick": {"kit": "rock", "phrase": "phrase_001", "bar": position}, "snare": {"kit": "rock", "phrase": "phrase_001", "bar": position},
                               "bell": {"kit": "latin", "phrase": "phrase_002", "bar": position}}


def test_lineage_of_a_padded_track_says_the_shorter_one_rests_there():
  long = _named(_track("rock", ["kick"], [_bar(kick={0}), _bar(kick={0}), _bar(kick={0})]), "phrase_001")
  short = _named(_track("latin", ["bell"], [_bar(bell={0})]), "phrase_002")
  lineage = lib.combine_tracks_lineage([long, short])
  assert [row["channels"]["bell"]["bar"] for row in lineage] == [1, None, None], "no source bar where the shorter phrase has ended"
  assert [row["channels"]["kick"]["bar"] for row in lineage] == [1, 2, 3]
  assert all(row["channels"]["bell"]["phrase"] == "phrase_002" and row["channels"]["bell"]["kit"] == "latin" for row in lineage), "the group still belongs to its phrase and kit"


def test_lineage_of_a_re_timed_track_records_the_tempo_it_came_with():
  a = _named(_track("rock", ["kick"], [_bar(tempo=100, kick={0}), _bar(tempo=90, kick={0})]), "phrase_001")
  b = _named(_track("latin", ["bell"], [_bar(tempo=100, bell={0}), _bar(tempo=95, bell={0})]), "phrase_002")
  lineage = lib.combine_tracks_lineage([a, b])
  assert [row["tempo_bpm"] for row in lineage] == [100, 90]
  assert lineage[0]["retimed_from"] == {}
  assert lineage[1]["retimed_from"] == {"latin": 95}, "only the kit whose own tempo was changed is named, with the tempo it had"


def test_lineage_without_phrase_names_says_none_and_a_muted_kit_has_no_channels_in_it():
  rock = _track("rock", ["kick"], [_bar(kick={0})])
  latin = dict(_track("latin", ["bell"], [_bar(bell={0})]), mute=True)
  lineage = lib.combine_tracks_lineage([rock, latin])
  assert lineage[0]["channels"] == {"kick": {"kit": "rock", "phrase": None, "bar": 1}}


# ---- 2026-10-29-0910: mute / solo / volume -------------------------------------------------------------------------------------------------------------------------------------------

def _channels_of(bars):
  return {c for bar in bars for c in bar["channels"]}


def test_a_muted_kit_contributes_no_channel_but_the_arrangement_keeps_its_length():
  rock = dict(_rock(), mute=True)                                          # 2 bars
  latin = _latin()                                                          # 1 bar
  out = lib.combine_tracks([rock, latin])
  assert len(out) == 2, "muting rock does not shorten the arrangement"
  assert _channels_of(out) == {"bell", "claves"}, "kick, snare and hihat are rock's: gone; latin's stray kick was never played"


def test_every_track_muted_is_a_plain_refusal_not_an_empty_score():
  with pytest.raises(ValueError, match="combine_tracks: every track is muted"):
    lib.combine_tracks([dict(_rock(), mute=True), dict(_latin(), mute=True)])


def test_solo_is_exactly_muting_every_other_kit():
  tracks = [_rock(), _track("bells", ["bell", "claves"], [_bar(claves={0, 3}, bell={0, 8})]), _track("congas", ["conga_high"], [_bar(conga_high={0, 4})])]
  for soloed in range(3):
    with_solo = copy.deepcopy(tracks); with_solo[soloed]["solo"] = True
    with_mutes = copy.deepcopy(tracks)
    for i, t in enumerate(with_mutes):
      if i != soloed: t["mute"] = True
    assert lib.combine_tracks(with_solo) == lib.combine_tracks(with_mutes)


def test_two_solos_play_together_and_solo_wins_over_mute_on_the_same_kit():
  tracks = [dict(_rock(), solo=True), dict(_track("bells", ["bell", "claves"], [_bar(claves={0, 3}, bell={0, 8})]), solo=True), _track("congas", ["conga_high"], [_bar(conga_high={0})])]
  assert _channels_of(lib.combine_tracks(tracks)) == {"kick", "snare", "hihat", "bell", "claves"}
  both = [dict(_rock(), solo=True, mute=True), _latin()]
  assert _channels_of(lib.combine_tracks(both)) == {"kick", "snare", "hihat"}, "asked to play it alone and muted: alone wins"


def test_volume_100_changes_nothing_and_the_default_is_100():
  assert lib.combine_tracks([dict(_rock(), volume=100), _latin()]) == lib.combine_tracks([_rock(), _latin()])


@pytest.mark.parametrize("hit,volume,expected", [(True, 50, 45), (90, 70, 63), (3, 50, 2), (1, 10, 1), (127, 99, 126), (127, 100, 127), (100, 1, 1), (2, 25, 1), (5, 10, 1)])
def test_volume_scales_a_velocity_rounded_half_up_and_clamped_to_1_127(hit, volume, expected):
  bar = _bar(kick={0: hit})
  out = lib.combine_tracks([dict(_track("rock", ["kick"], [bar]), volume=volume)])
  assert out[0]["channels"]["kick"][0] == expected


def test_volume_never_leaves_1_to_127_and_never_adds_or_loses_a_hit():
  rng = random.Random(7)
  for _ in range(200):
    steps = 16
    row = [rng.choice([False, True, rng.randint(1, 127)]) for _ in range(steps)]
    bar = {"time_signature": "4/4", "steps": steps, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100, "channels": {"kick": list(row)}}
    volume = rng.randint(1, 99)                                              # 100 leaves the row exactly as it was (a plain hit stays plain), tested on its own
    out = lib.combine_tracks([dict(_track("rock", ["kick"], [bar]), volume=volume)])[0]["channels"]["kick"]
    for before, after in zip(row, out):
      if before is False:
        assert after is False
      else:
        assert isinstance(after, int) and not isinstance(after, bool) and 1 <= after <= 127
    assert [v is not False for v in row] == [v is not False for v in out]


def test_volume_zero_is_a_muted_kit():
  assert lib.combine_tracks([dict(_rock(), volume=0), _latin()]) == lib.combine_tracks([dict(_rock(), mute=True), _latin()])


def test_mute_solo_volume_never_change_the_inputs():
  tracks = [dict(_rock(), volume=40, solo=True), _latin()]
  before = copy.deepcopy(tracks)
  lib.combine_tracks(tracks); lib.combine_tracks_lineage(tracks)
  assert tracks == before


@pytest.mark.parametrize("field,bad", [("mute", 1), ("mute", "yes"), ("solo", 0), ("solo", None), ("volume", True), ("volume", -1), ("volume", 101), ("volume", 50.5), ("volume", "70"), ("phrase", 3), ("phrase", "")])
def test_a_malformed_mute_solo_volume_or_phrase_is_refused_naming_the_function_and_the_kit(field, bad):
  with pytest.raises(ValueError, match="combine_tracks.*rock|rock.*combine_tracks"):
    lib.combine_tracks([dict(_rock(), **{field: bad})])


def test_two_kits_with_one_channel_are_still_refused_even_when_one_is_muted():
  with pytest.raises(ValueError, match="kick"):
    lib.combine_tracks([_rock(), dict(_rock(), kit="rock2", mute=True)])
