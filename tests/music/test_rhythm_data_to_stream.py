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


# ---------------------------------------------------------------------------------------------------
# Beat-as-data Phases 2+3 (drain 2026-10-04-2330): per-step velocity in the schema, and accent_mask.
# ---------------------------------------------------------------------------------------------------
import copy
import os
import tempfile

from music21 import converter


def _vels(part):
  """Per-hit velocities in the part, in time order (in-memory Note.volume.velocity)."""
  return [n.volume.velocity for n in part.flatten().notes]


def _midi_velocities_by_pitch(score):
  """Write the score to a real MIDI file and parse it back: {midi pitch: [velocity, ...] in time order}.
  The GM drum slot identifies the channel (kick 35 / snare 38 / closed hi-hat 42), so this reads what a
  MIDI player would actually play, not just the in-memory Note.volume."""
  fp = os.path.join(tempfile.mkdtemp(), "beat.mid")
  score.write("midi", fp=fp)
  out = {}
  for n in sorted(converter.parse(fp).flatten().notes, key=lambda n: float(n.offset)):
    # channel-10 hits parse back as Unpitched; the stored instrument's percMapPitch is the GM drum slot
    out.setdefault(n.storedInstrument.percMapPitch, []).append(n.volume.velocity)
  return out


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


# ---- schema: a step may be false/0 (rest), true (default velocity), or an int 1-127 -----------------

def test_int_step_values_become_hits_at_that_velocity_and_zero_or_false_are_rests():
  steps = [100, 0, False, 64, True, 0, 0, 0] + [False] * 8
  part = lib.rhythm_data_to_stream(_data(channels={"snare": steps})).parts[0]
  assert [off for off, _ in _hits(part)] == [0.0, 0.75, 1.0]        # steps 0, 3, 4; steps 1,2,5.. are rests
  assert _vels(part) == [100, 64, 90]                               # plain True in a mixed channel = 90


def test_plain_true_in_a_mixed_channel_uses_music21s_real_default_velocity_90_explicitly():
  # music21 leaves Note.volume.velocity None and its MIDI writer plays 90; the converter now sets 90
  # explicitly so a mixed channel is deterministic. Pin the number against the real MIDI writer.
  d = _data(channels={"kick": [True, True] + [False] * 14})
  plain = _midi_velocities_by_pitch(lib.rhythm_data_to_stream(d))[35]
  d["channels"]["kick"][1] = 120
  mixed = _midi_velocities_by_pitch(lib.rhythm_data_to_stream(d))[35]
  assert plain == [90, 90]
  assert mixed == [90, 120]


def test_all_boolean_data_is_unchanged_no_velocity_is_set():
  """Prompt §8: existing all-boolean data must behave identically — velocities are left untouched
  (None in memory, music21's default 90 on the wire), exactly as before this drain."""
  score = lib.rhythm_data_to_stream(_data(channels={"kick": _four_on_floor(), "hihat": [True] * 16}))
  for part in score.parts:
    assert set(_vels(part)) == {None}
  assert set(_midi_velocities_by_pitch(score)[42]) == {90}


def test_velocity_one_and_one_twenty_seven_are_the_inclusive_bounds():
  part = lib.rhythm_data_to_stream(_data(channels={"kick": [1, 127] + [0] * 14})).parts[0]
  assert _vels(part) == [1, 127]


@pytest.mark.parametrize("bad", ["x", "true", 1.5, 90.0, -1, 128, 1000, None, [1], {"v": 1}])
def test_invalid_step_values_raise_naming_channel_and_step_index(bad):
  steps = [False] * 16
  steps[5] = bad
  with pytest.raises(ValueError) as e:
    lib.rhythm_data_to_stream(_data(channels={"snare": steps}))
  msg = str(e.value)
  assert msg.startswith("rhythm_data_to_stream:")
  assert "'snare'" in msg and "step 5" in msg


def test_velocities_reach_the_written_midi_file_per_hit_in_step_order():
  d = _data(channels={"hihat": [120, 0, 60, 0, 90, 0, 30, 0] + [0] * 8, "kick": [True] + [False] * 15})
  by_pitch = _midi_velocities_by_pitch(lib.rhythm_data_to_stream(d))
  assert by_pitch[42] == [120, 60, 90, 30]
  assert by_pitch[35] == [90]


def test_velocity_is_per_channel_one_channels_ints_do_not_leak_into_another():
  d = _data(channels={"kick": [100] + [False] * 15, "snare": [True] + [False] * 15})
  score = lib.rhythm_data_to_stream(d)
  assert _vels(score.parts[0]) == [100]
  assert _vels(score.parts[1]) == [None]


# ---- accent_mask -------------------------------------------------------------------------------------

def test_accent_mask_hand_worked_straight_rock_by_syncopated():
  out = lib.accent_mask(_rock(), _synco())
  ch = out["channels"]
  hit_vel = lambda name: [v for v in ch[name] if v]
  assert hit_vel("kick") == [112, 72]
  assert hit_vel("snare") == [72, 112]
  assert hit_vel("hihat") == [112, 112, 72, 112, 72, 112, 112, 112]


def test_accent_mask_keeps_rests_exactly_where_base_has_them():
  out = lib.accent_mask(_rock(), _synco())
  for name, base_steps in _rock()["channels"].items():
    assert [bool(v) for v in out["channels"][name]] == [bool(v) for v in base_steps]
    assert all(v is False or v == 0 for v, b in zip(out["channels"][name], base_steps) if not b)


def test_accent_mask_keeps_base_metadata_and_channel_names():
  base = _rock()
  base.update(swing_pct=25, tempo_bpm=87)
  mask = _synco()
  mask.update(swing_pct=60, tempo_bpm=200)
  out = lib.accent_mask(base, mask)
  assert (out["time_signature"], out["steps"], out["group_size"]) == ("4/4", 16, 4)
  assert out["swing_pct"] == 25 and out["tempo_bpm"] == 87          # base wins (first input wins)
  assert list(out["channels"]) == ["kick", "snare", "hihat"]


def test_accent_mask_mask_hit_is_the_union_across_all_mask_channels():
  base = {**_rock(), "channels": {"hihat": [True] * 16}}
  mask = {**_synco(), "channels": {"kick": [i == 1 for i in range(16)], "snare": [i == 2 for i in range(16)]}}
  out = lib.accent_mask(base, mask)
  accented = [i for i, v in enumerate(out["channels"]["hihat"]) if v == 112]
  assert accented == [1, 2]                                         # a union, not an intersection


def test_accent_mask_mask_channel_restricts_the_mask_to_that_one_channel():
  base = {**_rock(), "channels": {"hihat": [True] * 16}}
  out = lib.accent_mask(base, _synco(), mask_channel="kick")
  assert [i for i, v in enumerate(out["channels"]["hihat"]) if v == 112] == [0, 3, 10]
  out = lib.accent_mask(base, _synco(), mask_channel="snare")
  assert [i for i, v in enumerate(out["channels"]["hihat"]) if v == 112] == [7, 12]


def test_accent_mask_unknown_mask_channel_raises():
  with pytest.raises(ValueError, match="accent_mask.*'cowbell'"):
    lib.accent_mask(_rock(), _synco(), mask_channel="cowbell")


def test_accent_mask_custom_accent_and_normal_values():
  out = lib.accent_mask(_rock(), _synco(), accent=127, normal=20)
  assert [v for v in out["channels"]["kick"] if v] == [127, 20]


def test_accent_mask_rests_stay_silent_even_where_the_mask_hits():
  base = {**_rock(), "channels": {"kick": [i == 8 for i in range(16)]}}
  mask = {**_synco(), "channels": {"kick": [True] * 16}}           # mask hits everywhere
  out = lib.accent_mask(base, mask)
  assert [v for v in out["channels"]["kick"] if v] == [112]
  assert sum(1 for v in out["channels"]["kick"] if v) == 1


def test_accent_mask_an_int_velocity_in_base_is_just_a_hit_and_is_overwritten():
  base = {**_rock(), "channels": {"kick": [33 if i in (0, 8) else 0 for i in range(16)]}}
  out = lib.accent_mask(base, _synco())
  assert [v for v in out["channels"]["kick"] if v] == [112, 72]


def test_accent_mask_never_mutates_its_inputs():
  base, mask = _rock(), _synco()
  base_before, mask_before = copy.deepcopy(base), copy.deepcopy(mask)
  out = lib.accent_mask(base, mask)
  assert base == base_before and mask == mask_before
  out["channels"]["kick"][0] = 1
  out["channels"]["kick"].append("x")
  assert base == base_before                                       # result shares no list with base


@pytest.mark.parametrize("field, value", [("steps", 12), ("time_signature", "3/4"), ("group_size", 2)])
def test_accent_mask_grid_mismatch_raises_naming_the_field(field, value):
  mask = _synco()
  if field == "steps":
    mask["channels"] = {k: v[:12] for k, v in mask["channels"].items()}
  mask[field] = value
  with pytest.raises(ValueError, match=rf"accent_mask.*{field}"):
    lib.accent_mask(_rock(), mask)


@pytest.mark.parametrize("kw", [{"accent": 0}, {"accent": 128}, {"accent": 1.5}, {"accent": True},
                                {"accent": "loud"}, {"normal": 0}, {"normal": 200}, {"normal": None}])
def test_accent_mask_validates_accent_and_normal_as_ints_1_to_127(kw):
  with pytest.raises(ValueError, match=r"accent_mask"):
    lib.accent_mask(_rock(), _synco(), **kw)


def test_accent_mask_rejects_non_dict_inputs_and_bad_steps_with_the_function_name():
  with pytest.raises(ValueError, match="accent_mask"):
    lib.accent_mask("nope", _synco())
  with pytest.raises(ValueError, match="accent_mask"):
    lib.accent_mask(_rock(), None)
  bad = _rock()
  bad["channels"]["kick"][3] = "x"
  with pytest.raises(ValueError, match=r"accent_mask.*'kick'.*step 3"):
    lib.accent_mask(bad, _synco())


def test_accent_mask_output_feeds_rhythm_data_to_stream_and_the_midi_carries_the_accents():
  score = lib.rhythm_data_to_stream(lib.accent_mask(_rock(), _synco()))
  by_pitch = _midi_velocities_by_pitch(score)
  assert by_pitch[35] == [112, 72]
  assert by_pitch[38] == [72, 112]
  assert by_pitch[42] == [112, 112, 72, 112, 72, 112, 112, 112]


def test_accent_mask_is_registered_as_a_music_domain_chip_in_both_executor_lists():
  from forge.core import executor
  assert callable(executor._domain_globals_for(["music"])["accent_mask"])
  # (not `is lib.accent_mask`: other suites reload the lib module, so identity is order-dependent)
  assert executor._FORGE_MUSIC_LIB_NAMES["accent_mask"].__name__ == "accent_mask"
  assert "accent_mask" in executor._MUSIC_LAZY_CHIP_NAMES


def test_the_two_example_notes_sequence_and_accented_compose_as_documented():
  """What rhythm_sequence / rhythm_accented do, via the real functions: sequence = two bars (straight
  rock then syncopated) with same-instrument staves merged; accented = one bar, accents per the mask."""
  seq = lib.sequence_list(sections=[lib.rhythm_data_to_stream(_rock()), lib.rhythm_data_to_stream(_synco())])
  assert [p.getInstrument().instrumentName for p in seq.parts] == ["Kick", "Snare", "Closed Hi-Hat"]
  for part in seq.parts:
    assert len(part.getElementsByClass("Measure")) == 2
  kick = seq.parts[0].flatten().notes
  assert [float(n.offset) for n in kick] == [0.0, 2.0, 4.0, 4.75, 6.5]   # rock 0,8 -> 0,2 ; synco 0,3,10 -> 4,4.75,6.5
