"""2026-11-23-1030 (pitch in bars, Stage 1a): a MELODY BAR is rhythm-data's pitched sibling. `rhythm_data_to_stream` sees `notes` (and no `channels`) and hands the data to
`melody_data_to_stream`: ONE pitched Part (one staff), the instrument's General MIDI program set, every note exactly as long as the steps it is given (a step is a sixteenth in 4/4).
The data: {time_signature, steps, group_size, tempo_bpm, instrument, notes: [{step (from 1), pitch, length (steps)}]}."""
import pytest
from music21 import clef, meter, note, tempo

from forge.music import lib


def _data(**over):
  d = {
    "time_signature": "4/4", "steps": 16, "group_size": 4, "tempo_bpm": 100,
    "instrument": "piano",
    "notes": [],
  }
  d.update(over)
  return d


def _n(step, pitch, length=1):
  return {"step": step, "pitch": pitch, "length": length}


def _notes(score):
  return [(int(n.pitch.midi), float(n.offset), float(n.quarterLength)) for n in score.parts[0].flatten().notes]


# ---- the dispatch: `notes` and no `channels` is a melody; the rhythm path is untouched -----------------------------------------------------------------------------------------------------

def test_notes_without_channels_go_to_the_melody_builder():
  score = lib.rhythm_data_to_stream(_data(notes=[_n(1, "G3")]))
  assert len(score.parts) == 1
  assert _notes(score) == [(55, 0.0, 0.25)]


def test_a_rhythm_bar_is_still_a_rhythm_bar():
  score = lib.rhythm_data_to_stream({"time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 120, "channels": {"kick": [i % 4 == 0 for i in range(16)]}})
  assert len(score.parts) == 1
  assert score.parts[0].getInstrument().midiChannel == 9          # a percussion Part on channel 10, exactly as before


def test_notes_next_to_channels_is_refused_in_words():
  with pytest.raises(ValueError, match="both channels and notes"):
    lib.rhythm_data_to_stream(_data(notes=[_n(1, "G3")], channels={"kick": [False] * 16}))


def test_melody_data_to_stream_can_be_called_directly():
  score = lib.melody_data_to_stream(_data(notes=[_n(1, "C4", 4)]))
  assert _notes(score) == [(60, 0.0, 1.0)]


# ---- pitch: the names a person writes, mapped to music21's --------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,midi", [
  ("C4", 60), ("G3", 55), ("D4", 62), ("B4", 71), ("A4", 69), ("C5", 72),
  ("Bb4", 70), ("B-4", 70),            # a flat is `b` after the letter (what a person writes) or `-` (music21's own name): the same note
  ("F#3", 54), ("C#4", 61), ("E-3", 51), ("Eb3", 51),
  ("c4", 60), ("bb4", 70),             # the letter's case does not matter
])
def test_pitch_names_map_to_midi_numbers(name, midi):
  assert _notes(lib.melody_data_to_stream(_data(notes=[_n(1, name)]))) == [(midi, 0.0, 0.25)]


def test_a_flat_is_written_as_a_flat_in_the_score():
  p = lib.melody_data_to_stream(_data(notes=[_n(1, "Bb4"), _n(2, "F#3")])).parts[0].flatten().notes
  assert (p[0].pitch.name, p[0].pitch.octave) == ("B-", 4)
  assert (p[1].pitch.name, p[1].pitch.octave) == ("F#", 3)


@pytest.mark.parametrize("bad", ["H4", "C", "4", "C#", "Cb", "C##4", "Cbb4", "C 4", "", "C4.5", 60, None, "C10", "C-1x"])
def test_a_pitch_that_is_not_a_note_name_with_an_octave_is_refused_naming_it(bad):
  with pytest.raises(ValueError, match="pitch"):
    lib.melody_data_to_stream(_data(notes=[_n(1, bad)]))


# ---- time: a step is exact, rests fill the gaps, nothing crosses the barline ----------------------------------------------------------------------------------------------------------------------

def test_offsets_and_lengths_are_exact_in_4_4():
  score = lib.melody_data_to_stream(_data(notes=[_n(1, "G3", 2), _n(5, "D4", 1), _n(9, "B4", 8)]))
  assert _notes(score) == [(55, 0.0, 0.5), (62, 1.0, 0.25), (71, 2.0, 2.0)]


def test_a_gap_is_one_rest_not_one_per_step():
  part = lib.melody_data_to_stream(_data(notes=[_n(1, "G3"), _n(9, "D4")])).parts[0].flatten()
  rests = [(float(r.offset), float(r.quarterLength)) for r in part.getElementsByClass(note.Rest)]
  assert rests == [(0.25, 1.75), (2.25, 1.75)]


def test_an_empty_bar_is_one_whole_bar_rest():
  part = lib.melody_data_to_stream(_data(notes=[])).parts[0].flatten()
  assert [(float(r.offset), float(r.quarterLength)) for r in part.getElementsByClass(note.Rest)] == [(0.0, 4.0)]
  assert list(part.notes) == []


def test_the_notes_may_be_given_in_any_order():
  assert _notes(lib.melody_data_to_stream(_data(notes=[_n(9, "D4"), _n(1, "G3")]))) == [(55, 0.0, 0.25), (62, 2.0, 0.25)]


def test_the_last_note_may_end_exactly_on_the_barline():
  assert _notes(lib.melody_data_to_stream(_data(notes=[_n(13, "G3", 4)]))) == [(55, 3.0, 1.0)]


def test_a_note_that_would_cross_the_barline_is_refused_in_words():
  with pytest.raises(ValueError, match="end inside the bar"):
    lib.melody_data_to_stream(_data(notes=[_n(15, "G3", 3)]))


def test_two_notes_on_one_step_are_refused_in_words():
  with pytest.raises(ValueError, match="one voice"):
    lib.melody_data_to_stream(_data(notes=[_n(1, "G3"), _n(1, "D4")]))


def test_a_note_that_starts_while_another_still_sounds_is_refused_in_words():
  with pytest.raises(ValueError, match="one voice"):
    lib.melody_data_to_stream(_data(notes=[_n(1, "G3", 4), _n(3, "D4")]))


def test_other_grids_3_4_and_6_8():
  three = lib.melody_data_to_stream(_data(time_signature="3/4", steps=12, notes=[_n(1, "C4", 12)]))
  assert _notes(three) == [(60, 0.0, 3.0)]
  six = lib.melody_data_to_stream(_data(time_signature="6/8", steps=6, group_size=3, notes=[_n(1, "C4", 3), _n(4, "D4", 3)]))
  assert _notes(six) == [(60, 0.0, 1.5), (62, 1.5, 1.5)]


# ---- the Part: meter, tempo, clef, instrument --------------------------------------------------------------------------------------------------------------------------------------------------

def test_the_part_carries_the_meter_and_the_tempo():
  part = lib.melody_data_to_stream(_data(tempo_bpm=84, notes=[_n(1, "G3")])).parts[0]
  assert part.flatten().getElementsByClass(meter.TimeSignature)[0].ratioString == "4/4"
  assert part.flatten().getElementsByClass(tempo.MetronomeMark)[0].number == 84


def test_the_clef_fits_the_notes():
  low = lib.melody_data_to_stream(_data(notes=[_n(1, "C2"), _n(5, "G2")])).parts[0].flatten()
  high = lib.melody_data_to_stream(_data(notes=[_n(1, "G3"), _n(5, "B4"), _n(9, "C5")])).parts[0].flatten()
  assert isinstance(low.getElementsByClass(clef.Clef)[0], clef.BassClef)
  assert isinstance(high.getElementsByClass(clef.Clef)[0], clef.TrebleClef)


@pytest.mark.parametrize("name,program", [("piano", 0), ("guitar", 24), ("mandolin", 25), ("violin", 40), ("cello", 42)])
def test_the_instrument_sets_the_general_midi_program(name, program):
  part = lib.melody_data_to_stream(_data(instrument=name, notes=[_n(1, "G3")])).parts[0]
  assert part.getInstrument().midiProgram == program


def test_the_mandolin_does_not_inherit_the_strings_program():
  # music21's Mandolin sets no program of its own and inherits 48 (string ensemble); a melody bar says what it means: steel guitar (25) is the nearest plucked, bright, double-course sound General MIDI has
  import music21
  assert music21.instrument.Mandolin().midiProgram == 48
  assert lib.melody_data_to_stream(_data(instrument="mandolin", notes=[_n(1, "G3")])).parts[0].getInstrument().midiProgram == 25


def test_the_instrument_name_is_read_in_any_case_and_an_unknown_one_lists_the_known():
  assert lib.melody_data_to_stream(_data(instrument="Cello", notes=[])).parts[0].getInstrument().midiProgram == 42
  with pytest.raises(ValueError, match="piano, guitar, mandolin, violin and cello"):
    lib.melody_data_to_stream(_data(instrument="kazoo"))


def test_the_musicxml_carries_the_midi_program_and_one_staff():
  from forge.core.serialization import serialize_result
  out = serialize_result(lib.rhythm_data_to_stream(_data(instrument="cello", notes=[_n(1, "G3"), _n(2, "D4"), _n(3, "B4"), _n(4, "A4")])), {"snippet_id": "t", "meta": {"title": "t"}})
  xml = out["content"]
  assert xml.count("<part id=") == 1
  assert "<midi-program>43</midi-program>" in xml          # MusicXML counts programs from 1: 43 is the cello
  assert "<sign>G</sign>" in xml


# ---- validation: the words ------------------------------------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["time_signature", "steps", "group_size", "tempo_bpm", "instrument", "notes"])
def test_a_missing_field_is_named(missing):
  d = _data(notes=[_n(1, "G3")]); del d[missing]
  with pytest.raises(ValueError, match=missing):
    lib.melody_data_to_stream(d)


def test_data_with_neither_notes_nor_channels_is_still_the_rhythm_bars_refusal():
  d = _data(); del d["notes"]
  with pytest.raises(ValueError, match="missing required field 'channels'"):
    lib.rhythm_data_to_stream(d)


@pytest.mark.parametrize("bad,match", [
  ({"steps": 0}, "steps"), ({"steps": True}, "steps"), ({"group_size": 5}, "group_size"), ({"tempo_bpm": 0}, "tempo_bpm"), ({"tempo_bpm": "fast"}, "tempo_bpm"),
  ({"notes": "G3"}, "notes"), ({"notes": [5]}, "note 1"), ({"notes": [{"step": 1, "pitch": "G3"}]}, "length"),
  ({"notes": [_n(0, "G3")]}, "step"), ({"notes": [_n(17, "G3")]}, "step"), ({"notes": [_n(1.5, "G3")]}, "step"), ({"notes": [_n(1, "G3", 0)]}, "length"), ({"notes": [_n(1, "G3", 1.5)]}, "length"),
  ({"notes": [{"step": 1, "pitch": "G3", "length": 1, "velocity": 90}]}, "velocity"),
])
def test_bad_data_is_refused_naming_the_field(bad, match):
  with pytest.raises(ValueError, match=match):
    lib.melody_data_to_stream(_data(**bad))


def test_data_that_is_not_a_dict_is_refused():
  with pytest.raises(ValueError, match="dict"):
    lib.melody_data_to_stream([1, 2])


def test_the_input_is_not_changed():
  d = _data(notes=[_n(9, "D4"), _n(1, "Bb4")])
  import copy
  before = copy.deepcopy(d)
  lib.melody_data_to_stream(d)
  assert d == before


# ---- the Prelude: the first two bars of BWV 1007 -----------------------------------------------------------------------------------------------------------------------------------------

BAR_1 = "G3 D4 B4 A4 B4 D4 B4 D4".split() * 2
BAR_2 = "G3 E4 C5 B4 C5 E4 C5 E4".split() * 2


def test_the_prelude_bars_1_and_2():
  b1 = lib.melody_data_to_stream(_data(instrument="cello", notes=[_n(i + 1, p) for i, p in enumerate(BAR_1)]))
  b2 = lib.melody_data_to_stream(_data(instrument="cello", notes=[_n(i + 1, p) for i, p in enumerate(BAR_2)]))
  assert [m for m, _, _ in _notes(b1)] == [55, 62, 71, 69, 71, 62, 71, 62] * 2
  assert [m for m, _, _ in _notes(b2)] == [55, 64, 72, 71, 72, 64, 72, 64] * 2
  assert [o for _, o, _ in _notes(b1)] == [i * 0.25 for i in range(16)]
  assert all(q == 0.25 for _, _, q in _notes(b1))
