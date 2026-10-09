"""Beat-as-data Phase 7 (drain 2026-10-07-1700): world-rhythm vocabulary — four new percussion channels (bell, claves,
conga_high, conga_low), the meters 12/8, 6/8 and 5/4 proven end to end, and the five new rhythm data notes executed through
the real engine from the music-theory SOURCE vault.

The existing behaviour (kick/snare/hihat, 4/4, 3/4, every shipped note) is pinned by test_rhythm_data_to_stream.py and
test_rhythm_example_notes.py, which are untouched and must stay green."""
import io
import os

import pytest
from music21 import meter, tempo

from forge.music import lib

_NEW = {  # channel -> (GM percussion key, MusicXML part name)
  "bell": (56, "Bell"),
  "claves": (75, "Claves"),
  "conga_high": (62, "High Conga"),
  "conga_low": (64, "Low Conga"),
}


def _data(ts="4/4", steps=16, group=4, tempo_bpm=100, **channels):
  return {"time_signature": ts, "steps": steps, "group_size": group, "swing_pct": 0,
          "tempo_bpm": tempo_bpm, "channels": channels}


def _hit(steps, at, value=True):
  return [value if i in at else False for i in range(steps)]


def _midi_notes(score):
  """Write the score to a real MIDI file and read the RAW note-on events back: [(GM key, velocity, MIDI channel index,
  offset in quarter lengths)] in time order. (Raw events on purpose: music21's higher-level MIDI reader names a key through
  its PercussionMapper, which has no entry for 75 / Claves, so it would hide exactly the byte this test needs.)"""
  import tempfile
  from music21 import midi
  fp = os.path.join(tempfile.mkdtemp(), "x.mid")
  score.write("midi", fp=fp)
  mf = midi.MidiFile()
  mf.open(fp)
  mf.read()
  mf.close()
  out = []
  for track in mf.tracks:
    t = 0
    for ev in track.events:
      if ev.isDeltaTime():
        t += ev.time
      elif ev.type == midi.ChannelVoiceMessages.NOTE_ON and ev.velocity:
        out.append((ev.pitch, ev.velocity, ev.channel - 1, t / mf.ticksPerQuarterNote))
  return sorted(out, key=lambda x: (x[3], x[0]))


def _musicxml(score):
  from music21.musicxml import m21ToXml
  return m21ToXml.GeneralObjectExporter(score).parse().decode("utf-8")


# ---- (a) the four channels ------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", sorted(_NEW.items()))
def test_each_new_channel_lands_on_its_general_midi_percussion_key_on_channel_ten(name, expected):
  key, _ = expected
  score = lib.rhythm_data_to_stream(_data(**{name: _hit(16, {0, 8})}))
  notes = _midi_notes(score)
  assert [(p, c) for p, _, c, _ in notes] == [(key, 9), (key, 9)]       # MIDI channel 10 is index 9
  assert [o for *_, o in notes] == [0.0, 2.0]
  assert score.parts[0].flatten().notes[0].pitch.midi == key


@pytest.mark.parametrize("name,expected", sorted(_NEW.items()))
def test_each_new_channel_has_its_part_name_in_the_musicxml(name, expected):
  _, part_name = expected
  xml = _musicxml(lib.rhythm_data_to_stream(_data(**{name: _hit(16, {0})})))
  assert f"<part-name>{part_name}</part-name>" in xml


def test_part_order_is_the_order_of_the_channels_in_the_data():
  d = _data(conga_low=_hit(16, {0}), bell=_hit(16, {1}), kick=_hit(16, {2}), claves=_hit(16, {3}))
  names = [p.getInstrument().instrumentName for p in lib.rhythm_data_to_stream(d).parts]
  assert names == ["Low Conga", "Bell", "Kick", "Claves"]


def test_the_registry_has_exactly_the_three_old_and_four_new_channels():
  assert sorted(lib._RHYTHM_CHANNEL_INSTRUMENTS) == sorted(["kick", "snare", "hihat", *_NEW])


def test_existing_channels_keep_their_meaning_and_gm_numbers():
  d = _data(kick=_hit(16, {0}), snare=_hit(16, {0}), hihat=_hit(16, {0}))
  assert sorted(p for p, *_ in _midi_notes(lib.rhythm_data_to_stream(d))) == [35, 38, 42]


def test_unknown_channel_is_still_rejected_and_the_message_lists_the_new_set():
  with pytest.raises(ValueError) as e:
    lib.rhythm_data_to_stream(_data(cowbell=_hit(16, {0})))
  msg = str(e.value)
  assert "cowbell" in msg
  for name in ("bell", "claves", "conga_high", "conga_low", "kick", "snare", "hihat"):
    assert f"'{name}'" in msg


def test_accent_mask_works_on_new_channels_without_change():
  base = _data(bell=[True] * 4 + [False] * 12)
  mask = _data(kick=_hit(16, {0, 2}))
  out = lib.accent_mask(base, mask)
  assert out["channels"]["bell"][:4] == [112, 72, 112, 72]
  assert lib.rhythm_data_to_stream(out).parts[0].flatten().notes[0].volume.velocity == 112


@pytest.mark.parametrize("style", ["repeat_with_fills", "building", "ghost_notes"])
def test_extend_rhythm_carries_a_new_channel_through_every_bar_untouched(style):
  d = _data(claves=_hit(16, {0, 3, 6, 10, 12}), kick=_hit(16, {0, 8}))
  bars = lib.extend_rhythm(d, bars=4, style=style)
  assert len(bars) == 4
  for bar in bars:
    assert bar["channels"]["claves"] == d["channels"]["claves"]


def test_extend_rhythm_still_rejects_other_grids_honestly_for_new_meters():
  with pytest.raises(ValueError, match="16-step"):
    lib.extend_rhythm(_data("12/8", 12, 3, bell=_hit(12, {0, 2})), bars=4, style="repeat_with_fills")
  with pytest.raises(ValueError, match="16-step"):
    lib.extend_rhythm(_data("5/4", 20, 4, conga_high=_hit(20, {0})), bars=4, style="building")


def test_kit_notation_gives_each_new_channel_its_own_staff_position_not_the_snare_fallback():
  from forge.core.serialization import serialize_result
  d = _data(bell=_hit(16, {0}), claves=_hit(16, {1}), conga_high=_hit(16, {2}), conga_low=_hit(16, {3}))
  payload = serialize_result(lib.rhythm_data_to_stream(d), {"snippet_id": "t", "meta": {"title": "t"}})
  assert payload["type"] == "musicxml" and payload["has_percussion"] is True
  kit = payload["kit_content"]
  import re
  unpitched = re.findall(r"<unpitched>(.*?)</unpitched>", kit, re.S)          # notes only (rests carry a display position too)
  positions = [m for u in unpitched for m in re.findall(r"<display-step>([A-G])</display-step>\s*<display-octave>(\d)</display-octave>", u)]
  # (the kit fold may split a note across voices, so compare the SET of positions: high conga, bell, claves, low conga)
  assert {f"{s}{o}" for s, o in positions} == {"B4", "B5", "D6", "G4"}
  assert "C5" not in [f"{s}{o}" for s, o in positions], "nothing fell back to the snare position"


# ---- (b) the meters ---------------------------------------------------------------------------------------------

METERS = [
  # (time_signature, steps, group_size, bar quarterLength, step quarterLength)
  ("4/4", 16, 4, 4.0, 0.25),
  ("3/4", 12, 4, 3.0, 0.25),
  ("12/8", 12, 3, 6.0, 0.5),
  ("6/8", 6, 3, 3.0, 0.5),
  ("5/4", 20, 4, 5.0, 0.25),
]


@pytest.mark.parametrize("ts,steps,group,bar_ql,step_ql", METERS)
def test_meter_bar_length_measure_total_and_time_signature(ts, steps, group, bar_ql, step_ql):
  d = _data(ts, steps, group, kick=_hit(steps, {0}), snare=[True] * steps)
  score = lib.rhythm_data_to_stream(d)
  for part in score.parts:
    measures = list(part.getElementsByClass("Measure"))
    assert len(measures) == 1, f"{ts}: one bar, got {len(measures)}"
    assert float(measures[0].duration.quarterLength) == bar_ql
    assert [t.ratioString for t in part.flatten().getElementsByClass(meter.TimeSignature)] == [ts]
  snare = score.parts[1].flatten().notes
  assert len(snare) == steps
  assert [float(n.offset) for n in snare] == [i * step_ql for i in range(steps)]


@pytest.mark.parametrize("ts,steps,group,bar_ql,step_ql", METERS)
def test_meter_midi_note_on_ticks_are_on_the_step_grid(ts, steps, group, bar_ql, step_ql):
  hits = {0, 2, steps - 1}
  score = lib.rhythm_data_to_stream(_data(ts, steps, group, claves=_hit(steps, hits)))
  offsets = [o for *_, o in _midi_notes(score)]
  assert offsets == [i * step_ql for i in sorted(hits)]


def test_12_8_with_group_3_has_four_groups_and_the_expected_bell_pattern_durations():
  bell = lib.rhythm_data_to_stream(_data("12/8", 12, 3, tempo_bpm=120, bell=_hit(12, {0, 2, 4, 5, 7, 9, 11}))).parts[0]
  notes = bell.flatten().notes
  assert [(float(n.offset), float(n.quarterLength)) for n in notes] == [
    (0.0, 1.0), (1.0, 1.0), (2.0, 0.5), (2.5, 1.0), (3.5, 1.0), (4.5, 1.0), (5.5, 0.5)]
  assert sum(float(n.quarterLength) for n in notes) == 6.0


def test_5_4_tempo_mark_is_quarter_note_bpm():
  score = lib.rhythm_data_to_stream(_data("5/4", 20, 4, tempo_bpm=90, conga_high=_hit(20, {0})))
  assert [m.number for m in score.parts[0].flatten().getElementsByClass(tempo.MetronomeMark)] == [90]


@pytest.mark.parametrize("ts,steps,group", [("12/8", 12, 5), ("5/4", 20, 3), ("6/8", 6, 4)])
def test_a_grid_that_is_not_a_whole_number_of_groups_is_still_rejected(ts, steps, group):
  with pytest.raises(ValueError, match="group_size"):
    lib.rhythm_data_to_stream(_data(ts, steps, group, kick=[False] * steps))


# ---- (e) the five notes through the real engine ----------------------------------------------------------------

_VAULT = os.path.expanduser("~/projects/music-theory")
_NOTES = os.path.join(_VAULT, "rhythm_data")
_NEW_NOTES = ["rhythm_pattern_tresillo", "rhythm_pattern_hemiola", "rhythm_pattern_bell_12_8",
              "rhythm_pattern_clave_son_3_2", "rhythm_pattern_tha_dhi_gi_na_thom"]
_have_notes = all(os.path.isfile(os.path.join(_NOTES, n + ".md")) for n in _NEW_NOTES)
needs_notes = pytest.mark.skipif(not _have_notes, reason="the five Phase 7 notes are not in the music-theory source vault")


def _load_json_block(name):
  import json
  import re
  text = open(os.path.join(_NOTES, name + ".md"), encoding="utf-8").read()
  m = re.search(r"```json\n(.*?)\n```", text, re.S)
  return json.loads(m.group(1)), text


@needs_notes
@pytest.mark.parametrize("name,hits_by_channel", [
  ("rhythm_pattern_tresillo", {"kick": [0, 6, 12]}),
  ("rhythm_pattern_hemiola", {"kick": [0, 6], "hihat": [0, 4, 8]}),
  ("rhythm_pattern_bell_12_8", {"bell": [0, 2, 4, 5, 7, 9, 11]}),
  ("rhythm_pattern_clave_son_3_2", {"claves": [0, 3, 6, 10, 12]}),
  ("rhythm_pattern_tha_dhi_gi_na_thom", {"conga_high": [0, 4, 8, 12], "conga_low": [16]}),
])
def test_each_note_has_exactly_the_literal_hits_the_prompt_pins(name, hits_by_channel):
  data, _ = _load_json_block(name)
  assert list(data["channels"]) == list(hits_by_channel)
  for ch, expected in hits_by_channel.items():
    got = [i for i, v in enumerate(data["channels"][ch]) if v is not False]
    assert got == expected, f"{name}.{ch}"
    assert len(data["channels"][ch]) == data["steps"]


@needs_notes
def test_note_headers_meters_and_tempos():
  expect = {
    "rhythm_pattern_tresillo": ("4/4", 16, 4, 100),
    "rhythm_pattern_hemiola": ("3/4", 12, 4, 120),
    "rhythm_pattern_bell_12_8": ("12/8", 12, 3, 120),
    "rhythm_pattern_clave_son_3_2": ("4/4", 16, 4, 100),
    "rhythm_pattern_tha_dhi_gi_na_thom": ("5/4", 20, 4, 90),
  }
  for name, (ts, steps, group, bpm) in expect.items():
    d, _ = _load_json_block(name)
    assert (d["time_signature"], d["steps"], d["group_size"], d["tempo_bpm"]) == (ts, steps, group, bpm), name
    assert d["swing_pct"] == 0


@needs_notes
def test_tha_dhi_gi_na_thom_velocities_are_the_pinned_ints():
  d, _ = _load_json_block("rhythm_pattern_tha_dhi_gi_na_thom")
  assert [d["channels"]["conga_high"][i] for i in (0, 4, 8, 12)] == [112, 80, 80, 80]
  assert d["channels"]["conga_low"][16] == 112
  score = lib.rhythm_data_to_stream(d)
  accents = [sum(any(type(a).__name__ == "Accent" for a in n.articulations) for n in p.flatten().notes) for p in score.parts]
  assert accents == [1, 1]           # tha and thom carry the accent mark; dhi/gi/na (80) do not
  assert sorted(v for _, v, _, _ in _midi_notes(score)) == [80, 80, 80, 112, 112]


@needs_notes
@pytest.mark.parametrize("name,counts", [
  ("rhythm_pattern_tresillo", {"Kick": 3}),
  ("rhythm_pattern_hemiola", {"Kick": 2, "Closed Hi-Hat": 3}),
  ("rhythm_pattern_bell_12_8", {"Bell": 7}),
  ("rhythm_pattern_clave_son_3_2", {"Claves": 5}),
  ("rhythm_pattern_tha_dhi_gi_na_thom", {"High Conga": 4, "Low Conga": 1}),
])
def test_each_note_runs_through_the_real_engine_with_the_hand_worked_hit_counts(name, counts):
  data, _ = _load_json_block(name)
  score = lib.rhythm_data_to_stream(data)
  got = {p.getInstrument().instrumentName: len(p.flatten().notes) for p in score.parts}
  assert got == counts


@needs_notes
def test_each_note_description_pins_its_literals():
  for name in _NEW_NOTES:
    _, text = _load_json_block(name)
    head = text.split("---")[1]
    assert "type: data" in head and "content_type: json" in head and "description:" in head
