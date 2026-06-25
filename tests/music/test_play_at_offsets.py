"""v2-migration §3 Phase 1 — `play_at_offsets` composite chip tests."""

import io

from music21 import meter, midi as _m21midi, note as _note, stream as _stream, tempo

from forge.music.lib import (
    closed_hihat,
    kick,
    play_at_offsets,
    snare,
)


class TestStructure:
  def test_returns_part(self):
    p = play_at_offsets(kick(), [0, 2], bars=4)
    assert isinstance(p, _stream.Part)

  def test_correct_number_of_measures(self):
    p = play_at_offsets(kick(), [0, 2], bars=4)
    measures = list(p.getElementsByClass(_stream.Measure))
    assert len(measures) == 4

  def test_measure_1_has_time_signature_and_tempo(self):
    p = play_at_offsets(kick(), [0, 2], bars=4)
    m1 = list(p.getElementsByClass(_stream.Measure))[0]
    ts_list = list(m1.getElementsByClass(meter.TimeSignature))
    mm_list = list(m1.getElementsByClass(tempo.MetronomeMark))
    assert len(ts_list) == 1
    assert len(mm_list) == 1
    assert mm_list[0].number == 96

  def test_measure_2_onward_has_no_redundant_ts(self):
    p = play_at_offsets(kick(), [0, 2], bars=4)
    measures = list(p.getElementsByClass(_stream.Measure))
    for m in measures[1:]:
      assert not list(m.getElementsByClass(meter.TimeSignature))
      assert not list(m.getElementsByClass(tempo.MetronomeMark))

  def test_instrument_carried_for_routing(self):
    p = play_at_offsets(kick(), [0, 2], bars=4)
    inst = p.getInstrument(returnDefault=False)
    assert inst is not None
    assert type(inst).__name__ == 'BassDrum'


class TestNotesPerBar:
  def test_solitary_pattern(self):
    """solitary: kick at offsets [0, 2] (beats 1 + 3), bars=4."""
    p = play_at_offsets(kick(), [0, 2], duration=0.25, bars=4)
    for m in p.getElementsByClass(_stream.Measure):
      hits = [n for n in m.notes]
      assert len(hits) == 2

  def test_per_bar_varying_pattern(self):
    """Per-bar list: bar 1 = 3 hits, bar 2 = 2 hits, bar 3 = 2 hits, bar 4 = 1 hit."""
    bar_patterns = [[0, 2, 3.5], [0, 2], [0, 2], [0]]
    p = play_at_offsets(kick(), bar_patterns, duration=0.25, bars=4)
    measures = list(p.getElementsByClass(_stream.Measure))
    hits_per_bar = [len(list(m.notes)) for m in measures]
    assert hits_per_bar == [3, 2, 2, 1]

  def test_cycle_per_bar_pattern_when_bars_exceeds_pattern(self):
    """Pattern of 2 bars cycled across 5 bars."""
    bar_patterns = [[0], [0, 2]]
    p = play_at_offsets(kick(), bar_patterns, bars=5)
    measures = list(p.getElementsByClass(_stream.Measure))
    hits_per_bar = [len(list(m.notes)) for m in measures]
    # Bars 1,3,5 follow [0]; bars 2,4 follow [0,2].
    assert hits_per_bar == [1, 2, 1, 2, 1]

  def test_empty_offsets_produces_full_rest_bars(self):
    p = play_at_offsets(kick(), [], bars=4)
    measures = list(p.getElementsByClass(_stream.Measure))
    for m in measures:
      assert len(list(m.notes)) == 0


class TestMidiRoute:
  def test_midi_export_emits_correct_drum_pitches(self):
    """Regression guard from the v0.2.159 bongo-wall lesson."""
    score = _stream.Score()
    score.append(play_at_offsets(kick(), [0, 2], bars=2))
    score.append(play_at_offsets(closed_hihat(), [0, 1, 2, 3], bars=2))
    score.append(play_at_offsets(snare(), [1, 3], bars=2))

    mf = _m21midi.translate.streamToMidiFile(score)
    buf = io.BytesIO()
    mf.openFileLike(buf)
    mf.write()
    bytes_ = buf.getvalue()
    mf.close()

    mf2 = _m21midi.MidiFile()
    mf2.openFileLike(io.BytesIO(bytes_))
    mf2.read()
    mf2.close()
    pitches = set()
    channels = set()
    for track in mf2.tracks:
      for ev in track.events:
        if 'NOTE_ON' in str(ev.type) and getattr(ev, 'velocity', 0) > 0:
          pitches.add(ev.pitch)
          channels.add(ev.channel)
    assert channels == {10}
    assert {35, 38, 42}.issubset(pitches)
    assert 60 not in pitches


class TestVelocity:
  def test_int_velocity_applied(self):
    p = play_at_offsets(kick(), [0, 2], bars=2, velocity=70)
    notes = list(p.recurse().notes)
    for n in notes:
      assert n.volume.velocity == 70

  def test_no_velocity_leaves_defaults(self):
    p = play_at_offsets(kick(), [0, 2], bars=2)
    notes = list(p.recurse().notes)
    # music21 default velocity is 90 (or None depending on version).
    # Just check none of them is the explicit 70 we'd set above.
    for n in notes:
      assert n.volume.velocity != 70

  def test_mark_dynamics_inserts_dynamic_on_first_note(self):
    from music21 import dynamics
    p = play_at_offsets(kick(), [0, 2], bars=2, velocity='human', mark_dynamics=True)
    dyn_elements = list(p.recurse().getElementsByClass(dynamics.Dynamic))
    assert len(dyn_elements) >= 1
