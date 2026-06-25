"""v2-spike Phase 1 tests — `play_at_beats` + `show_score` engine primitives.

`play_at_beats(instrument, beats)` builds a music21 Part with one Note per beat
position. The percMapPitch issue from v0.2.159 means tests must verify the
MIDI bytes route notes to the correct channel-10 drum slot — not just check
that a Note object exists at the right offset.

`show_score(score)` is a passthrough for the spike; future iterations may
emit explicit render hooks. The test just confirms it returns its input.
"""
import io

import pytest
from music21 import instrument as m21_inst
from music21 import note as m21_note
from music21 import stream as m21_stream

from forge.music.lib import (
    closed_hihat,
    kick,
    play_at_beats,
    show_score,
    snare,
)


class TestPlayAtBeats:
  def test_returns_part(self):
    part = play_at_beats(kick(), [1, 3])
    assert isinstance(part, m21_stream.Part)

  def test_carries_instrument_for_routing(self):
    inst = kick()
    part = play_at_beats(inst, [1, 3])
    # The instrument should be findable on the part — channel-10 routing
    # falls out of getInstrument(returnDefault=False) returning a
    # percussion factory's output.
    found = part.getInstrument(returnDefault=False)
    assert found is not None
    assert type(found).__name__ == 'BassDrum'

  def test_note_count_matches_beats(self):
    part = play_at_beats(kick(), [1, 3])
    notes = list(part.recurse().notes)
    assert len(notes) == 2

  def test_beats_are_1_indexed_to_quarter_offsets(self):
    # beat 1 → offset 0.0; beat 3 → offset 2.0
    part = play_at_beats(kick(), [1, 3])
    notes = list(part.recurse().notes)
    offsets = sorted(n.getOffsetInHierarchy(part) for n in notes)
    assert offsets == [0.0, 2.0]

  def test_default_quarter_duration(self):
    part = play_at_beats(kick(), [1, 3])
    for n in part.recurse().notes:
      assert n.quarterLength == 1.0

  def test_supports_floating_beat_positions(self):
    # beat 1.5 → offset 0.5 (the 'and' of 1)
    part = play_at_beats(closed_hihat(), [1, 1.5, 2, 2.5])
    notes = list(part.recurse().notes)
    offsets = sorted(n.getOffsetInHierarchy(part) for n in notes)
    assert offsets == [0.0, 0.5, 1.0, 1.5]

  def test_empty_beats_returns_empty_part(self):
    part = play_at_beats(kick(), [])
    notes = list(part.recurse().notes)
    assert notes == []
    # Instrument still attached.
    assert part.getInstrument(returnDefault=False) is not None

  def test_midi_export_emits_correct_drum_pitches(self):
    """Critical regression guard: per v0.2.159, music21's streamToMidiFile
    uses the NOTE's spelled pitch (not the Part Instrument's percMapPitch).
    play_at_beats must build notes whose MIDI export lands at the right
    drum slot (kick=35, snare=38, closed-hi-hat=42). Otherwise the spike
    note would replay the bongo-wall bug.
    """
    from music21 import midi as _m21midi

    score = m21_stream.Score()
    score.append(play_at_beats(kick(), [1, 3]))
    score.append(play_at_beats(closed_hihat(), [1, 2, 3, 4]))
    score.append(play_at_beats(snare(), [2, 4]))

    mf = _m21midi.translate.streamToMidiFile(score)
    buf = io.BytesIO()
    mf.openFileLike(buf)
    mf.write()
    midi_bytes = buf.getvalue()
    mf.close()

    mf2 = _m21midi.MidiFile()
    mf2.openFileLike(io.BytesIO(midi_bytes))
    mf2.read()
    mf2.close()
    note_on_pitches = set()
    note_on_channels = set()
    for track in mf2.tracks:
      for ev in track.events:
        if 'NOTE_ON' in str(ev.type) and getattr(ev, 'velocity', 0) > 0:
          note_on_pitches.add(ev.pitch)
          note_on_channels.add(ev.channel)

    # All percussion routed to channel 10.
    assert note_on_channels == {10}
    # Pitches must include kick (35), snare (38), closed-hi-hat (42).
    # Not pitch 60 (the bongo-wall pitch from v0.2.159's bug class).
    assert 35 in note_on_pitches, f'kick missing — pitches: {note_on_pitches}'
    assert 38 in note_on_pitches, f'snare missing — pitches: {note_on_pitches}'
    assert 42 in note_on_pitches, f'closed-hi-hat missing — pitches: {note_on_pitches}'
    assert 60 not in note_on_pitches, (
      'bongo bug regression — every percussion fired pitch 60 on channel 10'
    )


class TestShowScore:
  def test_returns_input(self):
    s = m21_stream.Score()
    s.append(play_at_beats(kick(), [1]))
    out = show_score(s)
    assert out is s

  def test_passthrough_works_with_any_score_shape(self):
    # Empty Score still flows through.
    s = m21_stream.Score()
    out = show_score(s)
    assert out is s
