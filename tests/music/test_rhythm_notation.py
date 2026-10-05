"""Beat-as-data Phase 4 §1(e) (drain 2026-10-05-2100): cleaner hit notation.

Each hit's WRITTEN duration is the gap to the next hit in the same channel (the last hit of a bar runs to the end
of the bar), so a hi-hat on every other sixteenth reads as eighth notes and a kick on beats 1 and 3 as half notes,
instead of a sixteenth followed by rests. NOTATION ONLY: note-on offsets, MIDI velocities and accent marks are
unchanged — pinned below against goldens captured from the code BEFORE this change."""
import hashlib
import json
import os
import tempfile

import pytest
from music21 import articulations as m21_articulations
from music21 import converter, note

from forge.music import lib


def _rock():
  return {"time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100,
          "channels": {"kick": [i in (0, 8) for i in range(16)], "snare": [i in (4, 12) for i in range(16)],
                       "hihat": [i % 2 == 0 for i in range(16)]}}


def _synco():
  return {"time_signature": "4/4", "steps": 16, "group_size": 4, "swing_pct": 0, "tempo_bpm": 100,
          "channels": {"kick": [i in (0, 3, 10) for i in range(16)], "snare": [i in (7, 12) for i in range(16)],
                       "hihat": [i in (2, 6, 10, 14) for i in range(16)]}}


def _waltz():
  return {"time_signature": "3/4", "steps": 12, "group_size": 4, "swing_pct": 0, "tempo_bpm": 90,
          "channels": {"kick": [i in (0, 4, 8) for i in range(12)], "hihat": [True] * 12}}


def _triplet():
  return {"time_signature": "4/4", "steps": 12, "group_size": 3, "swing_pct": 0, "tempo_bpm": 90,
          "channels": {"kick": [i in (0, 3, 6, 9) for i in range(12)], "snare": [i in (6,) for i in range(12)]}}


def _mixed():
  return {**_rock(), "channels": {"hihat": [127, 0, True, 0, 100, 0, 99, 0, 72, 0, 90] + [0] * 5, "snare": [False] * 16}}


def _notes(part):
  return [(float(n.offset), float(n.quarterLength)) for n in part.flatten().notes]


def _rests(part):
  return [(float(r.offset), float(r.quarterLength)) for r in part.flatten().getElementsByClass(note.Rest)]


def _bar_total(part):
  return [float(m.duration.quarterLength) for m in part.getElementsByClass("Measure")]


# ---- the written durations -------------------------------------------------------------------------------

def test_rock_hihat_reads_as_eighth_notes_with_no_rests_and_kick_as_half_notes():
  score = lib.rhythm_data_to_stream(_rock())
  kick, snare, hat = score.parts
  assert _notes(hat) == [(i * 0.5, 0.5) for i in range(8)] and _rests(hat) == []
  assert _notes(kick) == [(0.0, 2.0), (2.0, 2.0)] and _rests(kick) == []


def test_a_leading_rest_before_a_channels_first_hit_stays_and_the_last_hit_runs_to_the_end_of_the_bar():
  snare = lib.rhythm_data_to_stream(_rock()).parts[1]
  assert _rests(snare) == [(0.0, 1.0)]                                    # steps 0-3 are rest: the leading rest stays
  assert _notes(snare) == [(1.0, 2.0), (3.0, 1.0)]                        # gap to the next hit, then to the bar end


def test_syncopated_kick_uses_the_true_gaps_between_its_hits():
  kick = lib.rhythm_data_to_stream(_synco()).parts[0]
  assert _notes(kick) == [(0.0, 0.75), (0.75, 1.75), (2.5, 1.5)] and _rests(kick) == []


def test_every_measure_still_adds_up_to_the_bar_length():
  for data in (_rock(), _synco(), _waltz(), _triplet(), _mixed()):
    bar = 3.0 if data["time_signature"] == "3/4" else 4.0
    for part in lib.rhythm_data_to_stream(data).parts:
      assert _bar_total(part) == [bar], (data["time_signature"], part.getInstrument().instrumentName)


def test_a_hit_on_the_last_step_is_one_step_long_and_ends_at_the_bar_line():
  d = {**_rock(), "channels": {"kick": [i == 15 for i in range(16)]}}
  part = lib.rhythm_data_to_stream(d).parts[0]
  assert _rests(part) == [(0.0, 3.75)] and _notes(part) == [(3.75, 0.25)]


def test_an_all_rest_channel_is_still_one_bar_of_rest():
  part = lib.rhythm_data_to_stream({**_rock(), "channels": {"snare": [False] * 16}}).parts[0]
  assert _notes(part) == [] and _rests(part) == [(0.0, 4.0)]


def test_waltz_hits_every_beat_are_quarter_notes_and_the_bar_is_three_beats():
  kick = lib.rhythm_data_to_stream(_waltz()).parts[0]
  assert _notes(kick) == [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0)] and _rests(kick) == []


def test_a_non_dyadic_grid_leaves_no_stray_float_noise_rest_at_the_bar_end():
  for part in lib.rhythm_data_to_stream(_triplet()).parts:
    assert all(q > 1e-6 for _, q in _rests(part)), _rests(part)
    assert _bar_total(part) == [4.0]


@pytest.mark.parametrize("hit_steps", [[5], [0, 2, 5], [1], [1, 3, 5]])
def test_float_accumulation_never_leaves_a_nanoscopic_rest_at_the_end_of_the_bar(hit_steps):
  """A 6-step 4/4 grid has a step of 0.6666..., and the per-hit durations then sum to 4 - 4.4e-16, which an exact `cursor < bar`
  check turns into a 4e-16 Rest. Real grids hit this (found by search: 875 of ~10000 random patterns), so the end-of-bar check
  carries a tolerance."""
  d = {"time_signature": "4/4", "steps": 6, "group_size": 3, "swing_pct": 0, "tempo_bpm": 90,
       "channels": {"kick": [i in hit_steps for i in range(6)]}}
  part = lib.rhythm_data_to_stream(d).parts[0]
  assert all(q > 1e-6 for _, q in _rests(part)), _rests(part)
  assert all(q > 1e-6 for _, q in _notes(part))
  # Without the tolerance music21 turns the 4e-16 remainder into a whole 1.0 Rest and the measure overflows to 5 beats.
  assert _bar_total(part) == [4.0]
  assert _rests(part) == ([(0.0, hit_steps[0] * 4 / 6)] if hit_steps[0] else [])


# ---- what must NOT change ----------------------------------------------------------------------------------

def _ons(score):
  fp = os.path.join(tempfile.mkdtemp(), "a.mid")
  score.write("midi", fp=fp)
  return sorted((round(float(n.offset), 6), n.storedInstrument.percMapPitch, n.volume.velocity)
                for n in converter.parse(fp).flatten().notes)


def _accents(score):
  return [sum(any(isinstance(a, m21_articulations.Accent) for a in n.articulations) for n in p.flatten().notes)
          for p in score.parts]


# Captured from the code BEFORE this change (2026-10-05): sha256[:16] of the sorted (offset, GM drum slot, velocity)
# note-on events read back from a real MIDI write, the event count, and the per-part Accent counts.
GOLDEN = {
  "rock": ("e2a13c42e9d9c8dc", 12, [0, 0, 0]),
  "synco": ("572faf0a55141992", 9, [0, 0, 0]),
  "multiplex": ("aa2311f27d292692", 21, [0, 0, 0, 0, 0, 0]),
  "sequence": ("9c7249e87d0b04d4", 21, [0, 0, 0]),
  "accented": ("b0e562af28547690", 12, [1, 1, 6]),
  "waltz": ("27928e1ebcb40356", 15, [0, 0]),
  "triplet": ("8fe72070fde608b3", 5, [0, 0]),
  "mixed": ("9d9074d840fea0ee", 6, [2, 0]),
}


def _golden_cases():
  rock, synco = lib.rhythm_data_to_stream(_rock()), lib.rhythm_data_to_stream(_synco())
  return {
    "rock": rock, "synco": synco,
    "multiplex": lib.voices_list(sections=[rock, synco]),
    "sequence": lib.sequence_list(sections=[lib.rhythm_data_to_stream(_rock()), lib.rhythm_data_to_stream(_synco())]),
    "accented": lib.rhythm_data_to_stream(lib.accent_mask(_rock(), _synco())),
    "waltz": lib.rhythm_data_to_stream(_waltz()), "triplet": lib.rhythm_data_to_stream(_triplet()),
    "mixed": lib.rhythm_data_to_stream(_mixed()),
  }


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_note_on_offsets_velocities_and_accent_marks_are_exactly_what_they_were_before(name):
  """Compares PARSED NOTE-ON EVENTS, not raw MIDI bytes: a longer written note legitimately moves the note-off (and
  so changes the file's bytes) while the note-on, the drum slot and the velocity stay put."""
  score = _golden_cases()[name]
  digest, count, accents = GOLDEN[name]
  ons = _ons(score)
  assert (hashlib.sha256(json.dumps(ons).encode()).hexdigest()[:16], len(ons), _accents(score)) == (digest, count, accents)


# ---- play_at_offsets takes per-hit durations (the SAME placement algorithm, not a second one) ---------------

def test_play_at_offsets_accepts_one_duration_per_hit_and_a_scalar_still_works_as_before():
  from music21 import instrument as _i  # noqa: F401  (imported for parity with the other chips)
  per_hit = lib.play_at_offsets(lib.kick(), [0, 1, 3], duration=[1.0, 2.0, 1.0], bars=2)
  assert _notes(per_hit) == [(0.0, 1.0), (1.0, 2.0), (3.0, 1.0), (4.0, 1.0), (5.0, 2.0), (7.0, 1.0)]
  assert _rests(per_hit) == []
  scalar = lib.play_at_offsets(lib.kick(), [0, 2], duration=1.0, bars=1)
  assert _notes(scalar) == [(0.0, 1.0), (2.0, 1.0)] and _rests(scalar) == [(1.0, 1.0), (3.0, 1.0)]


def test_play_at_offsets_rejects_a_duration_list_that_does_not_match_the_hit_count():
  with pytest.raises(ValueError, match="duration"):
    lib.play_at_offsets(lib.kick(), [0, 1, 3], duration=[1.0, 1.0], bars=1)


def test_the_converter_hands_play_at_offsets_the_gaps_and_does_not_place_hits_itself():
  import inspect
  src = inspect.getsource(lib.rhythm_data_to_stream)
  assert "play_at_offsets(" in src and "note.Note(" not in src and "note.Rest(" not in src
