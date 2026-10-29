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


@pytest.mark.parametrize("field,value", [("time_signature", "3/4"), ("steps", 12), ("group_size", 3), ("tempo_bpm", 120), ("swing_pct", 30)])
def test_a_different_meter_steps_or_tempo_is_a_plain_refusal_naming_field_bar_and_kits(field, value):
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


def test_a_tempo_that_differs_only_in_a_bar_both_tracks_have_is_found_at_that_bar():
  a = _track("rock", ["kick"], [_bar(tempo=100, kick={0}), _bar(tempo=90, kick={0})])
  b = _track("latin", ["bell"], [_bar(tempo=100, bell={0}), _bar(tempo=95, bell={0})])
  with pytest.raises(ValueError, match="bar 2"):
    lib.combine_tracks([a, b])


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
