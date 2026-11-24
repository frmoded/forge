"""2026-11-24-1031 (pitch in bars, Stage 1b): PHRASES (and the compositions that play them) accept MELODY bars.

A phrase is ALL rhythm bars or ALL melody bars. The engine reads the kind of the bars it is given:
  * `rhythm_bars_to_stream` joins a list of melody bars into ONE Part (one staff): one clef for the whole run (the one that fits ALL its notes), the time signature once, a tempo mark where the tempo
    changes, the instrument once; a list that mixes the two kinds, or whose melody bars differ in grid or instrument, is refused in a plain sentence naming the bar;
  * `extend_rhythm` of a melody bar is a PLAIN REPEAT (style "repeat": N copies, nothing added, no tempo change); the rhythm styles (fills, building, ghost notes) and a tempo change are about beats and are
    refused in plain words ("That works on beats, not on notes."); the style "repeat" on a rhythm bar is refused too;
  * Mix, Morph, Thin out and Double up (`mix_rhythm`, `morph_rhythm`, `morph_rhythm_info`, `thin_out_bars`, `double_up_bars`) refuse a melody bar in the same words;
  * `combine_tracks` (an ARRANGEMENT on kits) refuses a melody phrase: a kit plays beats, and a melody track (an instrument instead of a kit) does not exist yet;
  * `compose_sections` (a COMPOSITION) accepts sections of melody bars (repeated, cut and joined as for rhythm bars); a composition plays beats OR notes, never both.
The rhythm output is byte for byte what it was: the digests at the bottom were taken from the engine of 2026-11-23 (before this change) and are pinned."""
import copy
import hashlib
import re

import pytest
from music21 import clef, meter, tempo

from forge.core.serialization import serialize_result
from forge.music import lib

# Bars 1 to 10 of the Prelude of Bach's Cello Suite No. 1 (BWV 1007), the cello line of scores/prelude_bwv1007_trimmed.md in the scratch vault bwv1007-mock: sixteen sixteenths a bar.
PRELUDE = [
  "G3 D4 B4 A4 B4 D4 B4 D4 G3 D4 B4 A4 B4 D4 B4 D4",
  "G3 E4 C5 B4 C5 E4 C5 E4 G3 E4 C5 B4 C5 E4 C5 E4",
  "G3 F#4 C5 B4 C5 F#4 C5 F#4 G3 F#4 C5 B4 C5 F#4 C5 F#4",
  "G3 G4 B4 A4 B4 G4 B4 G4 G3 G4 B4 A4 B4 G4 B4 F#4",
  "G3 E4 B4 A4 B4 G4 F#4 G4 E4 G4 F#4 G4 B3 D4 C#4 B3",
  "C#4 G4 A4 G4 A4 G4 A4 G4 C#4 G4 A4 G4 A4 G4 A4 G4",
  "F#4 A4 D5 C#5 D5 A4 G4 A4 F#4 A4 G4 A4 D4 F#4 E4 D4",
  "E3 B3 G4 F#4 G4 B3 G4 B3 E3 B3 G4 F#4 G4 B3 G4 B3",
  "E3 C#4 D4 E4 D4 C#4 B3 A3 G4 F#4 E4 D5 C#5 B4 A4 G4",
  "F#4 E4 D4 D5 A4 D5 F#4 A4 D4 E4 F#4 A4 G4 F#4 E4 D4",
]
MIDI_OF = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _midi(name):
  accidental = 1 if "#" in name else -1 if name[1:2] == "b" else 0
  return (int(name[-1]) + 1) * 12 + MIDI_OF[name[0]] + accidental


def _bar(pitches="G3 D4", tempo_bpm=100, instrument="cello", steps=16, ts="4/4", group=4, length=1):
  names = pitches.split() if isinstance(pitches, str) else pitches
  return {"time_signature": ts, "steps": steps, "group_size": group, "tempo_bpm": tempo_bpm, "instrument": instrument,
          "notes": [{"step": i * length + 1, "pitch": p, "length": length} for i, p in enumerate(names)]}


def _prelude_bars():
  return [_bar(line) for line in PRELUDE]


def _rhythm_bar(**over):
  d = {"time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100,
       "channels": {"kick": [True] + [False] * 15, "snare": [False] * 4 + [True] + [False] * 11}}
  d.update(over)
  return d


def _midis(score):
  return [int(n.pitch.midi) for n in score.parts[0].flatten().notes]


# ---- the join: ten bars of the Prelude are ONE Part ----------------------------------------------------------------------------------------------------------------------------------------------------

def test_ten_bars_of_the_prelude_are_one_part_with_one_hundred_and_sixty_notes_in_order():
  bars = _prelude_bars()                                                    # 16 notes of one sixteenth each
  score = lib.rhythm_bars_to_stream(bars)
  assert len(score.parts) == 1
  assert len(score.parts[0].getElementsByClass("Measure")) == 10
  assert [m.number for m in score.parts[0].getElementsByClass("Measure")] == list(range(1, 11))
  assert _midis(score) == [_midi(p) for line in PRELUDE for p in line.split()]
  assert len(_midis(score)) == 160


def test_the_joined_part_has_one_clef_one_time_signature_one_instrument_and_one_tempo_mark():
  part = lib.rhythm_bars_to_stream(_prelude_bars()).parts[0]
  assert len(list(part.flatten().getElementsByClass(clef.Clef))) == 1
  assert len(list(part.flatten().getElementsByClass(meter.TimeSignature))) == 1
  assert len(list(part.flatten().getElementsByClass(tempo.MetronomeMark))) == 1
  assert part.getInstrument().midiProgram == 42                              # the cello, as in the one-bar score
  assert part.getElementsByClass("Measure")[0].getElementsByClass(clef.Clef)[0].sign == "G"   # the Prelude lies mostly above middle C...


def test_one_clef_for_the_whole_run_is_the_one_that_fits_all_its_notes():
  low = [_bar("C2 G2 C3 G2"), _bar("D2 A2 D3 A2")]
  part = lib.rhythm_bars_to_stream(low).parts[0]
  clefs = list(part.flatten().getElementsByClass(clef.Clef))
  assert len(clefs) == 1 and clefs[0].sign == "F"
  mixed = [_bar("C2 G2 C3 G2"), _bar("C6 G5 C6 G5")]                         # one bar low, one bar high: never a clef change in the middle of the line
  assert len(list(lib.rhythm_bars_to_stream(mixed).parts[0].flatten().getElementsByClass(clef.Clef))) == 1


def test_a_tempo_mark_is_written_where_the_tempo_changes():
  bars = [_bar(tempo_bpm=100), _bar(tempo_bpm=100), _bar(tempo_bpm=80), _bar(tempo_bpm=80), _bar(tempo_bpm=100)]
  part = lib.rhythm_bars_to_stream(bars).parts[0]
  marks = [(m.number, mark.number) for m in part.getElementsByClass("Measure") for mark in m.getElementsByClass(tempo.MetronomeMark)]
  assert marks == [(1, 100), (3, 80), (5, 100)]


def test_a_list_of_one_melody_bar_has_the_notes_of_that_bar():
  one = _bar("G3 D4 B4 A4")
  assert _midis(lib.rhythm_bars_to_stream([one])) == _midis(lib.melody_data_to_stream(one))


def test_the_input_bars_are_not_changed_by_the_join():
  bars = _prelude_bars(); before = copy.deepcopy(bars)
  lib.rhythm_bars_to_stream(bars)
  assert bars == before


def test_the_notes_keep_their_lengths_and_rests_across_the_join():
  bars = [_bar("G3 D4", length=2), _bar("A3 E4", length=4)]
  part = lib.rhythm_bars_to_stream(bars).parts[0]
  offsets = [(int(m.number), float(n.offset), float(n.quarterLength), n.isRest) for m in part.getElementsByClass("Measure") for n in m.notesAndRests]
  assert offsets == [(1, 0.0, 0.5, False), (1, 0.5, 0.5, False), (1, 1.0, 3.0, True), (2, 0.0, 1.0, False), (2, 1.0, 1.0, False), (2, 2.0, 2.0, True)]


def test_the_forks_of_a_phrase_lie_over_the_bars_and_still_join():
  bars = [_bar("G3 D4")] * 4
  bars = [copy.deepcopy(b) for b in bars]
  bars[1] = _bar("A3 E4")                                                    # what the glue does with `Bar 2 is replaced by [[bar]]`
  assert _midis(lib.rhythm_bars_to_stream(bars)) == [55, 62, 57, 64, 55, 62, 55, 62]


# ---- refusals of the join, in plain words ---------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_a_phrase_is_all_rhythm_bars_or_all_melody_bars():
  with pytest.raises(ValueError, match=r"all rhythm bars or all melody bars.*bar 1 is a rhythm bar.*bar 0 is a melody bar"):
    lib.rhythm_bars_to_stream([_bar(), _rhythm_bar()])
  with pytest.raises(ValueError, match=r"all rhythm bars or all melody bars.*bar 2 is a melody bar.*bar 0 is a rhythm bar"):
    lib.rhythm_bars_to_stream([_rhythm_bar(), _rhythm_bar(), _bar()])


def test_melody_bars_of_two_instruments_are_refused_naming_the_bars():
  with pytest.raises(ValueError, match=r"one instrument.*bar 1 is for the piano.*bar 0 is for the cello"):
    lib.rhythm_bars_to_stream([_bar(), _bar(instrument="piano")])


def test_melody_bars_on_two_grids_are_refused_like_rhythm_bars():
  with pytest.raises(ValueError, match=r"bar 1 disagrees with bar 0 on steps"):
    lib.rhythm_bars_to_stream([_bar(), _bar(steps=8, group=4)])


def test_a_melody_bar_that_is_wrong_is_named_by_its_place():
  bad = _bar(); bad["notes"][0]["pitch"] = "H9"
  with pytest.raises(ValueError, match=r"bar 2: .*pitch"):
    lib.rhythm_bars_to_stream([_bar(), _bar(), bad])


def test_a_tempo_that_is_not_a_number_is_refused_naming_the_bar():
  bad = _bar(); bad["tempo_bpm"] = 0
  with pytest.raises(ValueError, match=r"bar 1"):
    lib.rhythm_bars_to_stream([_bar(), bad])


# ---- extend_rhythm: a PLAIN REPEAT -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_extend_of_a_melody_bar_in_the_repeat_style_is_n_copies():
  seed = _bar("G3 D4 B4 A4")
  out = lib.extend_rhythm(seed, bars=10, style="repeat")
  assert out == [seed] * 10
  assert len({id(b) for b in out}) == 10 and len({id(b["notes"]) for b in out}) == 10      # no list is shared between the bars (or with the seed)
  out[0]["notes"][0]["pitch"] = "C4"
  assert seed["notes"][0]["pitch"] == "G3" and out[1]["notes"][0]["pitch"] == "G3"


def test_a_repeat_of_one_bar_is_one_bar_and_of_64_bars_is_64():
  assert len(lib.extend_rhythm(_bar(), bars=1, style="repeat")) == 1
  assert len(lib.extend_rhythm(_bar(), bars=64, style="repeat")) == 64
  with pytest.raises(ValueError, match="bars must be an int from 1 to 64"):
    lib.extend_rhythm(_bar(), bars=65, style="repeat")


def test_a_repeated_melody_bar_is_drawn_as_one_staff():
  score = lib.rhythm_bars_to_stream(lib.extend_rhythm(_bar("G3 D4 B4 A4"), bars=4, style="repeat"))
  assert len(score.parts) == 1 and _midis(score) == [55, 62, 71, 69] * 4


@pytest.mark.parametrize("style", ["repeat_with_fills", "building", "ghost_notes"])
def test_the_rhythm_styles_are_about_beats_and_refuse_a_melody_bar_in_plain_words(style):
  with pytest.raises(ValueError, match=r"extend_rhythm: That works on beats, not on notes"):
    lib.extend_rhythm(_bar(), bars=4, style=style)


def test_a_tempo_change_is_about_beats_too():
  with pytest.raises(ValueError, match=r"extend_rhythm: That works on beats, not on notes"):
    lib.extend_rhythm(_bar(), bars=4, style="repeat", tempo_change_pct=-20)


def test_the_repeat_style_on_a_rhythm_bar_is_refused_in_plain_words():
  with pytest.raises(ValueError, match=r"extend_rhythm: a plain repeat is for melody bars"):
    lib.extend_rhythm(_rhythm_bar(), bars=4, style="repeat")


def test_an_unknown_style_of_a_rhythm_bar_is_still_the_old_refusal():
  with pytest.raises(ValueError, match="unknown style 'nope'"):
    lib.extend_rhythm(_rhythm_bar(), bars=4, style="nope")


# ---- the gates of the rhythm-only verbs -----------------------------------------------------------------------------------------------------------------------------------------------------------------------

BEATS = "That works on beats, not on notes"


def test_mix_refuses_a_melody_bar():
  for a, b in [(_bar(), _rhythm_bar()), (_rhythm_bar(), _bar()), (_bar(), _bar())]:
    with pytest.raises(ValueError, match=rf"mix_rhythm: .*{BEATS}"):
      lib.mix_rhythm(a, b)


def test_morph_refuses_a_melody_bar():
  for fn in (lib.morph_rhythm, lib.morph_rhythm_info):
    with pytest.raises(ValueError, match=rf"morph_rhythm: .*{BEATS}"):
      fn(_bar(), _rhythm_bar())
    with pytest.raises(ValueError, match=rf"morph_rhythm: .*{BEATS}"):
      fn(_rhythm_bar(), _bar())


def test_thin_out_and_double_up_refuse_melody_bars():
  with pytest.raises(ValueError, match=rf"thin_out_bars: .*{BEATS}"):
    lib.thin_out_bars([_bar(), _bar()], 1, 2)
  with pytest.raises(ValueError, match=rf"double_up_bars: .*{BEATS}"):
    lib.double_up_bars([_bar(), _bar()], 1, 2)


def test_an_arrangement_on_a_kit_refuses_a_melody_phrase_in_plain_words():
  tracks = [{"kit": "rock", "channels": ["kick", "snare", "hihat"], "bars": [_bar(), _bar()], "phrase": "phrase_101"}]
  for fn in (lib.combine_tracks, lib.combine_tracks_lineage):
    with pytest.raises(ValueError, match=r"kit 'rock' was given a melody phrase.*a kit plays beats, not notes.*melody track"):
      fn(tracks)


def test_an_arrangement_of_rhythm_phrases_next_to_a_melody_phrase_refuses_it_too():
  tracks = [{"kit": "rock", "channels": ["kick", "snare"], "bars": [_rhythm_bar()]}, {"kit": "latin", "channels": ["bell"], "bars": [_bar()]}]
  with pytest.raises(ValueError, match=r"kit 'latin' was given a melody phrase"):
    lib.combine_tracks(tracks)


# ---- compose_sections: a COMPOSITION plays a melody phrase -----------------------------------------------------------------------------------------------------------------------------------------------

def test_a_composition_of_melody_sections_repeats_cuts_and_joins_like_rhythm_sections():
  a = [_bar("G3 D4"), _bar("A3 E4")]; b = [_bar("C4 E4")]
  out = lib.compose_sections([{"bars": a, "length": 5, "source": "phrase_101"}, {"bars": b}])
  assert [x["notes"][0]["pitch"] for x in out] == ["G3", "A3", "G3", "A3", "G3", "C4"]
  assert out[0] is not a[0] and out[2] is not out[0]                                     # copies, as for rhythm bars
  assert _midis(lib.rhythm_bars_to_stream(out)) == [55, 62, 57, 64, 55, 62, 57, 64, 55, 62, 60, 64]


def test_the_lineage_of_a_melody_composition_names_the_section_and_the_bar():
  a = [_bar("G3 D4"), _bar("A3 E4")]
  lineage = lib.compose_sections_lineage([{"bars": a, "length": 3, "source": "phrase_101"}])
  assert lineage == [{"section": 1, "source": "phrase_101", "bar": 1, "tempo_bpm": 100}, {"section": 1, "source": "phrase_101", "bar": 2, "tempo_bpm": 100}, {"section": 1, "source": "phrase_101", "bar": 1, "tempo_bpm": 100}]


def test_a_composition_plays_beats_or_notes_never_both():
  with pytest.raises(ValueError, match=r"compose_sections: .*beats or notes, not both.*section 2 bar 1 is a melody bar.*section 1 bar 1 is a rhythm bar"):
    lib.compose_sections([{"bars": [_rhythm_bar()]}, {"bars": [_bar()]}])
  with pytest.raises(ValueError, match=r"beats or notes, not both.*section 2 bar 1 is a rhythm bar.*section 1 bar 1 is a melody bar"):
    lib.compose_sections_lineage([{"bars": [_bar()]}, {"bars": [_rhythm_bar()]}])


def test_melody_sections_must_share_one_meter_and_one_grid_as_rhythm_sections_do():
  with pytest.raises(ValueError, match=r"section 2 bar 1 has steps 8 but section 1 has 16"):
    lib.compose_sections([{"bars": [_bar()]}, {"bars": [_bar(steps=8, group=4)]}])


def test_a_melody_section_that_is_not_a_bar_is_refused_naming_the_place():
  broken = _bar(); del broken["tempo_bpm"]
  with pytest.raises(ValueError, match=r"section 1 bar 2 is missing required field 'tempo_bpm'"):
    lib.compose_sections([{"bars": [_bar(), broken]}])


def test_a_composition_of_melody_sections_of_two_instruments_is_refused_when_it_is_drawn():
  out = lib.compose_sections([{"bars": [_bar()]}, {"bars": [_bar(instrument="piano")]}])
  with pytest.raises(ValueError, match=r"one instrument"):
    lib.rhythm_bars_to_stream(out)


# ---- P3: the rhythm output is byte for byte what it was --------------------------------------------------------------------------------------------------------------------------------------------------

def _normalize(xml):
  seen = {}

  def sub(m):
    key = m.group(0)
    seen.setdefault(key, f"{m.group(1)}#{len(seen)}")
    return f'id="{seen[key]}"'
  xml = re.sub(r"<encoding-date>.*?</encoding-date>", "", xml)
  return re.sub(r'id="([PI])[0-9a-f]{32}"', sub, xml)


def _digest(score):
  out = serialize_result(score, {"snippet_id": "t", "meta": {"title": "t"}})
  h = hashlib.sha256()
  for k in ("content", "multi_staff_content", "kit_content", "multi_staff_midi_base64"):
    h.update(_normalize(str(out.get(k) or "")).encode())
  return h.hexdigest()[:16]


def _seed(**kw):
  d = {"time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100,
       "channels": {"kick": [True] + [False] * 3 + [False] * 12, "snare": [False] * 4 + [True] + [False] * 11, "hihat": [True, False] * 8}}
  d.update(kw)
  return d


def _p3_cases():
  a = _seed()
  b = _seed(tempo_bpm=120, channels={"kick": [True, False, False, True] + [False] * 12, "snare": [False] * 4 + [100] + [False] * 3 + [True] + [False] * 7})
  ex = lib.extend_rhythm(a, bars=6, style="repeat_with_fills", tempo_change_pct=-20)
  forked = lib.extend_rhythm(a, bars=4); forked[1] = b
  t = lib.double_up_bars(lib.thin_out_bars(ex, 2, 4, row="hihat", amount=0.5), 1, 2, row=None, grid=16)
  lat = _seed(channels={"bell": [True] * 4 + [False] * 12, "claves": [False, True] * 8})
  comb = lib.combine_tracks([{"kit": "rock", "channels": ["kick", "snare", "hihat"], "bars": lib.extend_rhythm(a, bars=3)}, {"kit": "latin", "channels": ["bell", "claves"], "bars": [lat, lat]}])
  comp = lib.compose_sections([{"bars": lib.extend_rhythm(a, bars=2), "length": 5, "source": "p"}, {"bars": comb, "length": 3}])
  return {
    "extend_fills": lib.rhythm_bars_to_stream(ex),
    "extend_building": lib.rhythm_bars_to_stream(lib.extend_rhythm(a, bars=4, style="building")),
    "extend_ghost": lib.rhythm_bars_to_stream(lib.extend_rhythm(a, bars=3, style="ghost_notes")),
    "extend_forked": lib.rhythm_bars_to_stream(forked),
    "single_bar": lib.rhythm_bars_to_stream([a]),
    "rhythm_data_to_stream": lib.rhythm_data_to_stream(b),
    "mix": lib.rhythm_bars_to_stream([lib.mix_rhythm(a, b, weight=0.6, threshold=0.5, ghost=True)]),
    "morph": lib.rhythm_bars_to_stream(lib.morph_rhythm(a, b, bars=4)),
    "transform": lib.rhythm_bars_to_stream(t),
    "arrangement": lib.rhythm_bars_to_stream(comb),
    "composition": lib.rhythm_bars_to_stream(comp),
  }


# 2026-11-24-1031 (deliberate): taken from the engine of 2026-11-23 (HEAD 3de4d21), before any melody gate was added
P3_DIGESTS = {
  "extend_fills": "d75c02ff10254564", "extend_building": "3952e1565561ea29", "extend_ghost": "06194be663a784ff", "extend_forked": "37ec0b6d2fadf1d2",
  "single_bar": "a3a0bbed1062d2ed", "rhythm_data_to_stream": "595454aac6d1cb0e", "mix": "e7018a72c88f9322", "morph": "061b86bbd0cb2ec4",
  "transform": "46a5a1c1af25886e", "arrangement": "2017a98ae9f76ea0", "composition": "f6d204d80a304f2e",
}


@pytest.mark.parametrize("name", sorted(P3_DIGESTS))
def test_rhythm_output_is_byte_for_byte_what_it_was(name):
  assert _digest(_p3_cases()[name]) == P3_DIGESTS[name]
