"""v0.3.x — tests for to_kit_notation + has_percussion (v0.2.143 cohort feature).

Per v0.2.143 prompt §3.4, 12 failing-first tests covering:
1. No-op on percussion-less score (piano-only).
2. Kick-only → voice 2 only.
3. Snare-only → voice 1 only.
4. Multi-instrument kick+snare+hihat → both voices populated; hihat has x-notehead.
5. Mixed bass+percussion → bass passes through, percussion folds.
6. note.id preservation across transformation.
7. Source Instrument reference preservation (via editorial misc).
8. (deferred: dynamic mark anchoring — flagged as v0.2.144 follow-up; music21's
   dynamic-mark anchoring API is fiddly and the cohort features ship without it.)
9. Voice ordering: voice 1 (hands, up) before voice 2 (feet, down).
10. has_percussion: True for percussion Score.
11. has_percussion: False for piano-only Score.
12. has_percussion: False for empty Score; to_kit_notation passes through.
"""

import pytest
from music21 import clef, instrument, note, stream

from forge.music.lib import (
  kick,
  snare,
  closed_hihat,
  open_hihat,
  has_percussion,
  to_kit_notation,
  _KIT_VOICE_HANDS,
  _KIT_VOICE_FEET,
)


def _make_perc_part(inst_factory, pitches_durations):
  """Build a single-instrument percussion Part with the given (pitch, ql)
  pairs. Pitch values can be arbitrary; the kit fold replaces them with
  the kit-staff position regardless of source pitch."""
  part = stream.Part()
  part.insert(0, inst_factory())
  for i, (p, ql) in enumerate(pitches_durations):
    n = note.Note(p)
    n.quarterLength = ql
    n.id = f"src_{i}"
    part.append(n)
  return part


def _make_piano_part():
  part = stream.Part()
  part.insert(0, instrument.Piano())
  part.append(note.Note('C4', quarterLength=1.0))
  return part


def _all_kit_notes(kit_part):
  """Walk the kit Part and return notes grouped by voice id."""
  out = {'1': [], '2': []}
  for voice in kit_part.getElementsByClass(stream.Voice):
    for n in voice.recurse().notes:
      out[voice.id].append(n)
  return out


# =====================================================================
# has_percussion
# =====================================================================

def test_has_percussion_true_for_percussion_score():
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  assert has_percussion(score) is True


def test_has_percussion_false_for_piano_only_score():
  score = stream.Score()
  score.append(_make_piano_part())
  assert has_percussion(score) is False


def test_has_percussion_false_for_empty_score():
  score = stream.Score()
  assert has_percussion(score) is False


def test_has_percussion_true_for_mixed_bass_plus_percussion():
  score = stream.Score()
  score.append(_make_piano_part())
  score.append(_make_perc_part(snare, [('E2', 1.0)]))
  assert has_percussion(score) is True


# =====================================================================
# to_kit_notation
# =====================================================================

def test_to_kit_notation_passthrough_on_percussion_less_score():
  """Piano-only Score → returns a Score with the piano Part unchanged."""
  score = stream.Score()
  score.append(_make_piano_part())
  out = to_kit_notation(score)
  out_parts = list(out.getElementsByClass(stream.Part))
  assert len(out_parts) == 1
  # The Part's instrument is still Piano.
  inst = out_parts[0].getInstrument(returnDefault=False)
  assert inst is not None
  assert type(inst).__name__ == 'Piano'


def test_to_kit_notation_kick_only_produces_voice_2_only():
  """Kick-only Part → output kit staff has voice 2 (feet, stems-down)
  populated; voice 1 (hands) empty.

  v0.2.145 — display position is F4 (just below the staff per kit
  convention), not B1 like the v0.2.143 literal-pitch version.
  """
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0), ('B2', 1.0)]))
  out = to_kit_notation(score)
  out_parts = list(out.getElementsByClass(stream.Part))
  assert len(out_parts) == 1
  kit = out_parts[0]
  notes_by_voice = _all_kit_notes(kit)
  assert len(notes_by_voice['1']) == 0
  assert len(notes_by_voice['2']) == 2
  # Stems down for voice 2.
  for n in notes_by_voice['2']:
    assert n.stemDirection == 'down'
  # v0.2.145 — Unpitched displayName F4 (kit-convention kick position).
  assert isinstance(notes_by_voice['2'][0], note.Unpitched)
  assert notes_by_voice['2'][0].displayName == 'F4'


def test_to_kit_notation_snare_only_produces_voice_1_only():
  score = stream.Score()
  score.append(_make_perc_part(snare, [('E3', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  notes_by_voice = _all_kit_notes(kit)
  assert len(notes_by_voice['1']) == 1
  assert len(notes_by_voice['2']) == 0
  # v0.2.145 — Unpitched displayName C5 (snare middle line).
  assert isinstance(notes_by_voice['1'][0], note.Unpitched)
  assert notes_by_voice['1'][0].displayName == 'C5'
  assert notes_by_voice['1'][0].stemDirection == 'up'


def test_to_kit_notation_multi_instrument_kick_snare_hihat():
  """Kick+snare+closed-hihat → voice 1 has snare+hihat, voice 2 has kick.
  Hihat carries notehead='x'."""
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  score.append(_make_perc_part(snare, [('E3', 1.0)]))
  score.append(_make_perc_part(closed_hihat, [('F3', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  notes_by_voice = _all_kit_notes(kit)
  assert len(notes_by_voice['1']) == 2  # snare + hihat
  assert len(notes_by_voice['2']) == 1  # kick
  # v0.2.145 — hihat displayName G5 (above staff); snare C5 (middle).
  hihat_notes = [n for n in notes_by_voice['1'] if n.displayName == 'G5']
  snare_notes = [n for n in notes_by_voice['1'] if n.displayName == 'C5']
  assert len(hihat_notes) == 1
  assert len(snare_notes) == 1
  assert hihat_notes[0].notehead == 'x'
  # Snare's notehead is the music21 default; check it's not 'x'.
  assert snare_notes[0].notehead != 'x'


def test_to_kit_notation_open_hihat_gets_circle_x_notehead():
  score = stream.Score()
  score.append(_make_perc_part(open_hihat, [('F3', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  notes_by_voice = _all_kit_notes(kit)
  assert len(notes_by_voice['1']) == 1
  assert notes_by_voice['1'][0].notehead == 'circle-x'


def test_to_kit_notation_mixed_score_passes_non_percussion_through():
  """Bass+percussion → output has bass Part unchanged + kit Part."""
  score = stream.Score()
  score.append(_make_piano_part())
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  out = to_kit_notation(score)
  out_parts = list(out.getElementsByClass(stream.Part))
  assert len(out_parts) == 2
  # First part should be piano (passed through).
  inst_0 = out_parts[0].getInstrument(returnDefault=False)
  assert type(inst_0).__name__ == 'Piano'
  # Second part should be the kit fold (has voice 2 with kick).
  kit = out_parts[1]
  notes_by_voice = _all_kit_notes(kit)
  assert len(notes_by_voice['2']) == 1


def test_to_kit_notation_preserves_note_ids():
  """note.id is preserved from source notes to kit-staff notes."""
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0), ('B2', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  notes_by_voice = _all_kit_notes(kit)
  ids = sorted(n.id for n in notes_by_voice['2'])
  assert ids == ['src_0', 'src_1']


def test_to_kit_notation_preserves_source_instrument_via_editorial():
  """Each kit-staff note carries a reference to its source Instrument
  in note.editorial.misc['forge_source_instrument']. MIDI export walks
  per-note instrument context, so channel-10 routing remains intact."""
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  notes_by_voice = _all_kit_notes(kit)
  src_inst = notes_by_voice['2'][0].editorial.misc.get('forge_source_instrument')
  assert src_inst is not None
  assert type(src_inst).__name__ == 'BassDrum'


def test_to_kit_notation_voice_ordering_hands_before_feet():
  """Voice 1 (hands/stems-up) should be inserted before Voice 2
  (feet/stems-down) in the kit Part's voices list."""
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  score.append(_make_perc_part(snare, [('E3', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  voices = list(kit.getElementsByClass(stream.Voice))
  assert [v.id for v in voices] == ['1', '2']


def test_to_kit_notation_does_not_mutate_input():
  """Input Score's Parts should remain untouched after to_kit_notation."""
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  # Snapshot before.
  orig_parts = list(score.getElementsByClass(stream.Part))
  orig_part_count = len(orig_parts)
  orig_first_inst = type(orig_parts[0].getInstrument(returnDefault=False)).__name__
  # Run.
  _ = to_kit_notation(score)
  # Snapshot after.
  post_parts = list(score.getElementsByClass(stream.Part))
  assert len(post_parts) == orig_part_count
  assert type(post_parts[0].getInstrument(returnDefault=False)).__name__ == orig_first_inst


def test_to_kit_notation_includes_percussion_clef_in_kit_part():
  """The kit Part should carry a PercussionClef so Verovio renders the
  5-line staff with percussion conventions."""
  score = stream.Score()
  score.append(_make_perc_part(snare, [('E3', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  clefs = list(kit.getElementsByClass(clef.PercussionClef))
  assert len(clefs) == 1


# =====================================================================
# v0.2.145 — Unpitched migration sanity checks (per v0345 §3.2)
# =====================================================================


def test_to_kit_notation_uses_unpitched_class():
  """v0.2.145 — all notes in the kit Part should be note.Unpitched
  instances (no plain Note). This is the structural guarantee for
  Verovio engraving: Unpitched serializes to <unpitched> + <display-
  step> + <display-octave> MusicXML, which Verovio honors for kit-
  convention staff positioning. Pre-v0.2.145 used Note with literal
  pitches, which Verovio positioned by absolute pitch (driver's
  spike 2026-06-26 confirmed the failure)."""
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  score.append(_make_perc_part(snare, [('E3', 1.0)]))
  score.append(_make_perc_part(closed_hihat, [('F3', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  notes_by_voice = _all_kit_notes(kit)
  all_notes = notes_by_voice['1'] + notes_by_voice['2']
  assert len(all_notes) > 0
  for n in all_notes:
    assert isinstance(n, note.Unpitched), (
      f"expected note.Unpitched but got {type(n).__name__}; "
      f"v0.2.145 Unpitched migration must apply to every kit-staff note")


def test_to_kit_notation_unpitched_displayname_is_kit_convention():
  """v0.2.145 — each note's displayName should match the kit convention
  position from _KIT_NOTATION_MAP."""
  score = stream.Score()
  score.append(_make_perc_part(kick, [('B2', 1.0)]))
  score.append(_make_perc_part(snare, [('E3', 1.0)]))
  score.append(_make_perc_part(closed_hihat, [('F3', 1.0)]))
  out = to_kit_notation(score)
  kit = list(out.getElementsByClass(stream.Part))[0]
  notes_by_voice = _all_kit_notes(kit)
  # Voice 2 has kick at F4.
  assert notes_by_voice['2'][0].displayName == 'F4'
  # Voice 1 has snare (C5) + hihat (G5).
  display_names = sorted(n.displayName for n in notes_by_voice['1'])
  assert display_names == ['C5', 'G5']
