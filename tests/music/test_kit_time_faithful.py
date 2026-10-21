"""The Kit view is time-faithful (drain 2026-10-21-1930; CC Iteration 99 found it on music-playground/bars/bar_004).

SYMPTOM: for a bar with two or more HAND channels (snare, hi-hat, bell, claves, congas) whose hits overlap in time, `kit_content`'s hands voice ran longer than the bar
(bar_004: 23 steps in a 12-step bar), so the Kit view showed notation that is not what the Beat Box plays.

MECHANISM (measured, see the drain's FEEDBACK §2): `to_kit_notation` puts every hand channel's notes into ONE music21 Voice at each channel's own offsets. A channel's note rings until
that channel's next hit, so two channels' notes overlap, and music21's MusicXML exporter lays a Voice's notes END TO END (it never writes <chord/> for separate Unpitched notes
and never <backup> inside a voice): the overlapped time is added instead of shared. The in-memory stream is right (the offsets are right); its SERIALIZATION is not (intuition I27).
`rhythm_data_to_stream` builds one Part per channel (the multi-staff view, faithful) and is not involved.

These tests go through the PRODUCTION path (data -> `rhythm_data_to_stream` -> `serialize_result`, the plugin's two calls), not `to_kit_notation` in isolation, and read the MusicXML
the way a renderer does (`kit_corpus.kit_report`).
"""
import hashlib
import json
from fractions import Fraction

import pytest

from tests.music import kit_corpus as kc

FROZEN = kc.FIXTURES / "kit_frozen"
INDEX = json.loads((FROZEN / "index.json").read_text())
BARS = kc.all_bars()


# ---- the checker itself must be able to fail on the original incident ---------------------------------------------------------------------------------------------------

def test_the_checker_flags_the_original_incident():
  """`kit_frozen/bar_004.xml` is the PRE-FIX Kit XML of bar_004 (generated from commit c8923e8). A checker that says it is fine checks nothing."""
  problems = kc.faithfulness_problems(kc.named_bars()["bar_004"], (FROZEN / "bar_004.xml").read_text())
  assert any("voice 1 is 23/4 quarters long in a 3-quarter bar" in p for p in problems), problems
  assert any("hits differ from the data" in p for p in problems), problems


def test_the_checker_passes_a_faithful_kit():
  assert kc.faithfulness_problems(kc.named_bars()["bar_001"], (FROZEN / "bar_001.xml").read_text()) == []


def test_the_report_reads_chords_backups_and_ties_like_a_renderer():
  xml = ('<score-partwise><part id="P"><measure number="1"><attributes><divisions>4</divisions></attributes>'
         '<note><unpitched><display-step>C</display-step><display-octave>5</display-octave></unpitched><duration>8</duration><voice>1</voice></note>'
         '<note><chord/><unpitched><display-step>B</display-step><display-octave>5</display-octave></unpitched><duration>8</duration><voice>1</voice><notehead>x</notehead></note>'
         '<note><unpitched><display-step>C</display-step><display-octave>5</display-octave></unpitched><duration>4</duration><tie type="start"/><voice>1</voice></note>'
         '<note><unpitched><display-step>C</display-step><display-octave>5</display-octave></unpitched><duration>4</duration><tie type="stop"/><voice>1</voice></note>'
         '<backup><duration>16</duration></backup>'
         '<note><unpitched><display-step>F</display-step><display-octave>4</display-octave></unpitched><duration>16</duration><voice>2</voice></note>'
         '</measure></part></score-partwise>')
  m = kc.kit_report(xml)[0]
  assert m["voices"]["1"]["end"] == 16 and m["voices"]["2"]["end"] == 16
  assert m["voices"]["1"]["notes"] == [(0, "C5", "normal"), (0, "B5", "x"), (8, "C5", "normal")], "a chord note shares the onset; a tie tail is not a new hit"


# ---- the bug, through the production path ----------------------------------------------------------------------------------------------------------------------------------

def test_bar_004_kit_voices_sum_to_the_bar():
  """THE REPORTED CASE: 4 channels, 3/4, 12 steps. Pre-fix voice 1 was 23/4 quarters long in a 3-quarter bar."""
  data = kc.named_bars()["bar_004"]
  rep = kc.kit_report(kc.kit_xml_for(data, "bar_004"))
  assert len(rep) == 1
  bar = 3 * rep[0]["divisions"]
  assert {v: r["end"] for v, r in rep[0]["voices"].items()} == {"1": bar, "2": bar}


@pytest.mark.parametrize("name", sorted(BARS))
def test_kit_view_is_time_faithful_for_every_bar(name):
  """Every voice is as long as the bar, and every hit of the data is in the Kit view at its own time and position, none invented. 133 bars: the 13 awkward ones the M3
  inspector was checked on, and 120 generated ones (all meters/shapes the Beat Box offers, 1-7 channels, plain and velocity hits)."""
  data = BARS[name]
  assert kc.faithfulness_problems(data, kc.kit_xml_for(data, name)) == []


# ---- P3: what is correct today stays byte-identical ---------------------------------------------------------------------------------------------------------------------------

def _sha(text):
  return hashlib.sha256(text.encode()).hexdigest()


def test_frozen_index_covers_the_corpus_and_is_not_vacuous():
  assert set(INDEX["bars"]) == set(BARS), "the frozen index and the corpus must list the same bars (regenerate with fixtures/kit_frozen/generate.py)"
  correct = [n for n, b in INDEX["bars"].items() if b["faithful_prefix"]]
  broken = [n for n, b in INDEX["bars"].items() if not b["faithful_prefix"]]
  assert len(correct) >= 30 and len(broken) >= 30, (len(correct), len(broken))
  assert {"bar_001", "bar_002", "bar_003", "eight_step_44", "six_eight"} <= set(correct)
  assert {"bar_004", "swung", "two_on_one_step", "all_seven"} <= set(broken)
  assert INDEX["prefix_commit"] == "c8923e82be678517d454f6a42d809a7ea6f33666"


@pytest.mark.parametrize("name", sorted(n for n, b in INDEX["bars"].items() if b["faithful_prefix"]))
def test_a_kit_view_that_was_correct_is_byte_identical(name):
  """The frozen digest is of the PRE-FIX engine's output (commit c8923e8, normalised: music21's random part/instrument ids and the date). Only the broken bars may change."""
  data = BARS[name]
  assert _sha(kc.normalise(kc.kit_xml_for(data, name))) == INDEX["bars"][name]["sha256"]


@pytest.mark.parametrize("name", sorted(BARS))
def test_multi_staff_view_and_midi_are_untouched(name):
  """Drain §4: the fix may change the Kit view only."""
  payload = kc.payload_for(BARS[name], name)
  assert _sha(kc.normalise(payload["multi_staff_content"])) == INDEX["bars"][name]["multi_staff_sha256"]
  assert _sha(payload.get("multi_staff_midi_base64") or "") == INDEX["bars"][name]["midi_sha256"]


# ---- the fold itself (direct): what the fix builds, and what it leaves alone ----------------------------------------------------------------------------------------------

def _fold(bar_data):
  from forge.music.lib import rhythm_data_to_stream, to_kit_notation
  kit = list(to_kit_notation(rhythm_data_to_stream(bar_data)).parts)[0]
  return {v.id: list(v.notes) for v in kit.getElementsByClass("Measure")[0].voices}


def _bar(**channels):
  steps = 16
  return {"time_signature": "4/4", "steps": steps, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100,
          "channels": {ch: [i in hits for i in range(steps)] for ch, hits in channels.items()}}


def test_hits_that_start_together_become_one_chord_and_every_member_keeps_its_identity():
  from music21 import percussion
  hands = _fold(_bar(snare=[0, 8], bell=[0, 4, 8, 12]))["1"]
  chords = [n for n in hands if isinstance(n, percussion.PercussionChord)]
  assert len(chords) == 2 and len(hands) == 4, "steps 0 and 8 are chords (snare+bell); steps 4 and 12 are the bell alone"
  for c in chords:
    positions = sorted(m.displayName for m in c.notes)
    assert positions == ["B5", "C5"]
    assert {type(m.storedInstrument).__name__ for m in c.notes} == {"SnareDrum", "Cowbell"}
    assert {m.notehead for m in c.notes} == {"normal", "x"}
    assert all(m.stemDirection == "up" for m in c.notes)
    assert all(m.editorial.misc["forge_source_instrument"] is m.storedInstrument for m in c.notes)
    assert {m.quarterLength for m in c.notes} == {c.quarterLength} == {1.0}, "a chord lasts until the next onset of the voice (step 4 / 12), 1 quarter"


def test_a_note_is_cut_at_the_next_onset_of_its_voice_not_at_its_own_channels_next_hit():
  """snare rings 0..8 and the bell hits at 4: the snare note must end at 4 or the voice runs long."""
  hands = _fold(_bar(snare=[0], bell=[4]))["1"]
  assert [(float(n.offset), float(n.quarterLength)) for n in hands] == [(0.0, 1.0), (1.0, 3.0)]


def test_a_voice_with_no_overlap_is_not_touched_each_note_keeps_its_own_length_and_the_gap_stays_a_gap():
  from music21 import instrument, note, stream
  from forge.music.lib import snare, to_kit_notation
  part = stream.Part()
  part.insert(0, snare())
  for off in (0.0, 2.0):
    n = note.Note("E3"); n.quarterLength = 0.5; part.insert(off, n)
  score = stream.Score(); score.append(part)
  kit = list(to_kit_notation(score).parts)[0]
  hands = [n for v in kit.getElementsByClass(stream.Voice) if v.id == "1" for n in v.notes]
  assert [(float(n.offset), float(n.quarterLength)) for n in hands] == [(0.0, 0.5), (2.0, 0.5)]


def test_the_feet_voice_gets_the_same_treatment():
  """kick and pedal hi-hat both go to voice 2; the rule is per voice, not per hand."""
  from music21 import instrument, note, percussion, stream
  from forge.music.lib import kick, to_kit_notation
  pedal = instrument.HiHatCymbal(); pedal.percMapPitch = 44
  def part(inst, ql):
    p = stream.Part(); p.insert(0, inst); n = note.Note("C3"); n.quarterLength = ql; p.insert(0, n); return p
  score = stream.Score(); score.append(part(kick(), 4.0)); score.append(part(pedal, 2.0))
  kit = list(to_kit_notation(score).parts)[0]
  feet = [n for v in kit.getElementsByClass(stream.Voice) if v.id == "2" for n in v.notes]
  assert len(feet) == 1 and isinstance(feet[0], percussion.PercussionChord) and sorted(m.displayName for m in feet[0].notes) == ["D4", "F4"]
  assert feet[0].quarterLength == 4.0, "a chord lasts as long as its LONGEST member (here a hand-built score: the members' own lengths differ)"


def test_the_feet_voice_gets_the_same_treatment_in_a_measured_score():
  """The production path (measures). Rhythm data cannot put two channels in the feet voice, so this builds the Score by hand: kick + pedal hi-hat starting together, then a kick."""
  from music21 import instrument, meter, note, percussion, stream
  from forge.music.lib import kick, to_kit_notation
  pedal = instrument.HiHatCymbal(); pedal.percMapPitch = 44
  def part(inst, hits):
    p = stream.Part(); p.insert(0, inst)
    m = stream.Measure(number=1); m.timeSignature = meter.TimeSignature("4/4")
    for off, ql in hits:
      n = note.Note("C3"); n.quarterLength = ql; m.insert(off, n)
    p.append(m); return p
  score = stream.Score(); score.append(part(kick(), [(0.0, 2.0), (2.0, 2.0)])); score.append(part(pedal, [(0.0, 3.0)]))
  kit = list(to_kit_notation(score).parts)[0]
  feet = [v for v in kit.getElementsByClass("Measure")[0].voices if v.id == "2"][0].notes
  assert [(float(n.offset), float(n.quarterLength), type(n).__name__) for n in feet] == [(0.0, 2.0, "PercussionChord"), (2.0, 2.0, "Unpitched")]
