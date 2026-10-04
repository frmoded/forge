"""Beat-as-data Phase 1 (drain 2026-10-03-0930): rhythm_data_to_stream converts the
rhythm_box widget's exported JSON into a Score with one percussion Part per channel."""
import pytest
from music21 import note, tempo, meter

from forge.music import lib


def _data(**over):
  d = {
    "time_signature": "4/4", "steps": 16, "group_size": 4,
    "swing_pct": 0, "tempo_bpm": 120,
    "channels": {"kick": [False] * 16},
  }
  d.update(over)
  return d


def _hits(part):
  f = part.flatten()
  return [(float(n.offset), float(n.quarterLength)) for n in f.notes]


def _rests(part):
  f = part.flatten()
  return [(float(r.offset), float(r.quarterLength)) for r in f.getElementsByClass(note.Rest)]


def _four_on_floor():
  return [i % 4 == 0 for i in range(16)]


def test_single_channel_hit_placement_is_exact():
  score = lib.rhythm_data_to_stream(_data(channels={"kick": _four_on_floor()}))
  assert len(score.parts) == 1
  # Four 16th-note hits on the beats: offsets 0,1,2,3, each one step (0.25 ql) long.
  assert _hits(score.parts[0]) == [(0.0, 0.25), (1.0, 0.25), (2.0, 0.25), (3.0, 0.25)]


def test_runs_of_false_steps_coalesce_into_one_rest():
  score = lib.rhythm_data_to_stream(_data(channels={"kick": _four_on_floor()}))
  # Three false steps between hits -> ONE 0.75 rest each, not three 0.25 rests; 4 hits -> 4 rests.
  assert _rests(score.parts[0]) == [(0.25, 0.75), (1.25, 0.75), (2.25, 0.75), (3.25, 0.75)]


def test_multi_channel_each_channel_is_its_own_part_with_its_instrument():
  d = _data(channels={
    "kick": _four_on_floor(),
    "snare": [i in (4, 12) for i in range(16)],
    "hihat": [True] * 16,
  })
  score = lib.rhythm_data_to_stream(d)
  assert len(score.parts) == 3
  names = [p.getInstrument().instrumentName for p in score.parts]
  assert names == ["Kick", "Snare", "Closed Hi-Hat"]
  assert [len(_hits(p)) for p in score.parts] == [4, 2, 16]
  assert _hits(score.parts[1]) == [(1.0, 0.25), (3.0, 0.25)]


def test_all_false_channel_is_one_bar_of_rest_and_no_notes():
  score = lib.rhythm_data_to_stream(_data(channels={"snare": [False] * 16}))
  part = score.parts[0]
  assert _hits(part) == []
  assert _rests(part) == [(0.0, 4.0)]


def test_waltz_three_four_uses_twelve_steps_and_a_three_beat_bar():
  d = _data(time_signature="3/4", steps=12, channels={"kick": [i in (0, 4, 8) for i in range(12)]})
  part = lib.rhythm_data_to_stream(d).parts[0]
  assert _hits(part) == [(0.0, 0.25), (1.0, 0.25), (2.0, 0.25)]
  assert _rests(part)[-1] == (2.25, 0.75)   # bar is 3.0 long, not 4.0


def test_every_part_carries_time_signature_and_tempo_on_measure_one():
  d = _data(tempo_bpm=96, channels={"kick": _four_on_floor(), "hihat": [True] * 16})
  for part in lib.rhythm_data_to_stream(d).parts:
    f = part.flatten()
    assert [m.number for m in f.getElementsByClass(tempo.MetronomeMark)] == [96]
    assert [t.ratioString for t in f.getElementsByClass(meter.TimeSignature)] == ["4/4"]


def test_hits_land_on_the_channel_ten_percussion_pitch_of_their_instrument():
  d = _data(channels={"kick": [True] + [False] * 15, "snare": [True] + [False] * 15,
                      "hihat": [True] + [False] * 15})
  midis = [p.flatten().notes[0].pitch.midi for p in lib.rhythm_data_to_stream(d).parts]
  assert midis == [35, 38, 42]   # BassDrum default percMapPitch, snare, closed hi-hat


def test_placement_matches_drum_chorus_own_bar_construction():
  """Anti-divergence guard (prompt §8: ONE hit/rest placement algorithm). In 12/8 (bar 6.0 ql,
  step 0.5 = an eighth) with kick on offsets 0 and 3.0, drum_chorus('standard') bar 1 kick and
  this converter's kick must produce identical (offset, length) hits and rests."""
  steps = 12
  kick_steps = [i in (0, 6) for i in range(steps)]
  mine = lib.rhythm_data_to_stream(
    _data(time_signature="12/8", steps=steps, group_size=3, channels={"kick": kick_steps})
  ).parts[0]
  theirs = lib.drum_chorus(profile="standard").parts[0]       # first Part is the kick
  assert theirs.getInstrument().instrumentName == "Kick"
  bar1 = theirs.getElementsByClass("Measure")[0]
  their_hits = [(float(n.offset), float(n.quarterLength)) for n in bar1.notes]
  their_rests = [(float(r.offset), float(r.quarterLength)) for r in bar1.getElementsByClass(note.Rest)]
  assert _hits(mine) == their_hits
  assert _rests(mine) == their_rests


def test_composes_with_voices_and_sequence_unchanged():
  a = lib.rhythm_data_to_stream(_data(channels={"kick": _four_on_floor(), "hihat": [True] * 16}))
  b = lib.rhythm_data_to_stream(_data(channels={"snare": [i in (4, 12) for i in range(16)]}))
  layered = lib.voices(a, b)
  assert len(layered.parts) == 3
  seq = lib.sequence(a, b)
  # Same-instrument parts merge across inputs; kick/hihat/snare each span 2 bars (one rest bar + one played).
  assert all(len(p.getElementsByClass("Measure")) == 2 for p in seq.parts)


def test_registered_as_a_music_domain_chip():
  from forge.core import executor
  assert callable(executor._domain_globals_for(["music"])["rhythm_data_to_stream"])


@pytest.mark.parametrize("bad, why", [
  (lambda d: d.pop("channels"), "missing field"),
  (lambda d: d.update(channels={"cowbell": [False] * 16}), "unknown channel"),
  (lambda d: d.update(channels={"kick": [False] * 15}), "wrong length"),
  (lambda d: d.update(group_size=5), "group_size not dividing steps"),
  (lambda d: d.update(steps=0), "non-positive steps"),
  (lambda d: d.update(swing_pct=101), "swing out of range"),
  (lambda d: d.update(channels={}), "empty channels"),
])
def test_invalid_data_raises_value_error_instead_of_guessing(bad, why):
  d = _data()
  bad(d)
  with pytest.raises(ValueError):
    lib.rhythm_data_to_stream(d)


def test_non_dict_input_raises():
  with pytest.raises(ValueError):
    lib.rhythm_data_to_stream("not a dict")
