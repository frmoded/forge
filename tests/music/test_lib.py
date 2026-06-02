import pytest
from music21 import key, meter, note, pitch, stream, instrument

from forge.music.lib import (
  bar, voices, sequence, repeat,
  minor_pentatonic, major_pentatonic,
  with_velocity,
  closed_hihat, open_hihat, pedal_hihat,
  low_tom, mid_tom, high_tom,
  crash_cymbal, ride_cymbal,
  kick, snare,
)


# ---------- bar ----------

def test_bar_default_time_signature_is_4_4():
  m = bar(note.Note('C4', quarterLength=1))
  ts = next(m.getElementsByClass(meter.TimeSignature), None)
  assert ts is not None
  assert ts.ratioString == '4/4'


def test_bar_pads_short_items_with_trailing_rest():
  m = bar(note.Note('C4', quarterLength=1), note.Note('D4', quarterLength=1))
  notes_and_rests = list(m.notesAndRests)
  assert len(notes_and_rests) == 3
  assert isinstance(notes_and_rests[-1], note.Rest)
  assert notes_and_rests[-1].duration.quarterLength == 2.0


def test_bar_does_not_pad_when_full():
  items = [note.Note('C4', quarterLength=1) for _ in range(4)]
  m = bar(*items)
  assert sum(n.duration.quarterLength for n in m.notesAndRests) == 4.0
  assert all(isinstance(n, note.Note) for n in m.notesAndRests)


def test_bar_respects_explicit_time_signature():
  m = bar(
    note.Note('C4', quarterLength=1.5),
    time_signature=meter.TimeSignature('6/8'),
  )
  ts = next(m.getElementsByClass(meter.TimeSignature))
  assert ts.ratioString == '6/8'
  assert sum(n.duration.quarterLength for n in m.notesAndRests) == 3.0


def test_bar_sets_measure_number():
  m = bar(note.Rest(quarterLength=4), number=7)
  assert m.number == 7


def test_bar_empty_items_pads_full_rest():
  m = bar()
  rests = list(m.notesAndRests)
  assert len(rests) == 1
  assert isinstance(rests[0], note.Rest)
  assert rests[0].duration.quarterLength == 4.0


def test_bar_overflow_raises():
  with pytest.raises(ValueError, match=r"bar\(\): items total .* but bar is"):
    bar(
      note.Note('C4', quarterLength=3),
      note.Note('D4', quarterLength=3),
    )


def test_bar_overflow_message_includes_durations():
  with pytest.raises(ValueError) as exc:
    bar(
      note.Note('C4', quarterLength=3),
      note.Note('D4', quarterLength=2),
      time_signature=meter.TimeSignature('4/4'),
    )
  assert '5' in str(exc.value)
  assert '4' in str(exc.value)


def test_bar_deepcopies_input_so_caller_can_reuse():
  shared = note.Note('C4', quarterLength=1)
  m1 = bar(shared)
  m2 = bar(shared)
  # mutating the copy in m1 must not affect m2 — proves no shared reference
  m1_note = next(m1.notes)
  m1_note.pitch.name = 'D'
  assert next(m2.notes).pitch.name == 'C'


# ---------- voices ----------

def test_voices_one_part_per_input():
  p1 = stream.Part(); p1.append(note.Note('C4', quarterLength=4))
  p2 = stream.Part(); p2.append(note.Note('E4', quarterLength=4))
  s = voices(p1, p2)
  parts = list(s.getElementsByClass(stream.Part))
  assert len(parts) == 2


def test_voices_assigns_instruments_by_index():
  p1 = stream.Part(); p1.append(note.Note('C4'))
  p2 = stream.Part(); p2.append(note.Note('E4'))
  s = voices(p1, p2, instruments=['Acoustic Guitar', 'Piano'])
  parts = list(s.getElementsByClass(stream.Part))
  inst1 = next(parts[0].getElementsByClass(instrument.Instrument))
  inst2 = next(parts[1].getElementsByClass(instrument.Instrument))
  assert isinstance(inst1, instrument.AcousticGuitar)
  assert isinstance(inst2, instrument.Piano)


def test_voices_instruments_length_mismatch_raises():
  p1 = stream.Part(); p1.append(note.Note('C4'))
  p2 = stream.Part(); p2.append(note.Note('E4'))
  with pytest.raises(ValueError, match="must match"):
    voices(p1, p2, instruments=['Piano'])


def test_voices_accepts_a_bare_measure():
  m = bar(note.Note('C4', quarterLength=4))
  s = voices(m)
  parts = list(s.getElementsByClass(stream.Part))
  assert len(parts) == 1
  assert len(list(parts[0].getElementsByClass(stream.Measure))) == 1


def test_voices_unpacks_multipart_score_input():
  # Common case: snippets return Scores, and voices() must accept multi-Part
  # Scores by unpacking each Part into the output rather than collapsing.
  p1 = stream.Part(); p1.append(note.Note('C4'))
  p2 = stream.Part(); p2.append(note.Note('E4'))
  multi = stream.Score(); multi.insert(0, p1); multi.insert(0, p2)
  out = voices(multi)
  assert len(list(out.getElementsByClass(stream.Part))) == 2


def test_voices_unpacks_multiple_multipart_scores():
  # voices(chorus_score, solo_score) where both have multiple parts:
  # output Part count == sum of input Part counts.
  c1 = stream.Part(); c1.append(note.Note('C4'))
  c2 = stream.Part(); c2.append(note.Note('E4'))
  chorus = stream.Score(); chorus.insert(0, c1); chorus.insert(0, c2)

  s1 = stream.Part(); s1.append(note.Note('G4'))
  solo = stream.Score(); solo.insert(0, s1)

  out = voices(chorus, solo)
  assert len(list(out.getElementsByClass(stream.Part))) == 3


def test_voices_instrument_applies_to_every_part_from_one_input():
  # When an input contributes multiple Parts, the matching instrument label
  # is assigned to all of them.
  p1 = stream.Part(); p1.append(note.Note('C4'))
  p2 = stream.Part(); p2.append(note.Note('E4'))
  multi = stream.Score(); multi.insert(0, p1); multi.insert(0, p2)

  solo_part = stream.Part(); solo_part.append(note.Note('G4'))

  out = voices(multi, solo_part, instruments=['Piano', 'Acoustic Guitar'])
  parts = list(out.getElementsByClass(stream.Part))
  assert len(parts) == 3
  insts = [next(p.getElementsByClass(instrument.Instrument)) for p in parts]
  guitar_count = sum(isinstance(i, instrument.AcousticGuitar) for i in insts)
  piano_count = sum(isinstance(i, instrument.Piano) for i in insts)
  assert piano_count == 2
  assert guitar_count == 1


# ---------- sequence ----------

def test_sequence_concatenates_single_part_inputs():
  p1 = stream.Part()
  p1.append(bar(note.Note('C4', quarterLength=4), number=1))
  p2 = stream.Part()
  p2.append(bar(note.Note('D4', quarterLength=4), number=1))
  s = sequence(p1, p2)
  parts = list(s.getElementsByClass(stream.Part))
  assert len(parts) == 1
  measures = list(parts[0].getElementsByClass(stream.Measure))
  assert [m.number for m in measures] == [1, 2]


def test_sequence_renumbers_measures_sequentially():
  p1 = stream.Part()
  p1.append(bar(note.Rest(quarterLength=4), number=5))
  p1.append(bar(note.Rest(quarterLength=4), number=6))
  p2 = stream.Part()
  p2.append(bar(note.Rest(quarterLength=4), number=99))
  s = sequence(p1, p2)
  measures = list(s.getElementsByClass(stream.Part)[0]
                  .getElementsByClass(stream.Measure))
  assert [m.number for m in measures] == [1, 2, 3]


def test_sequence_concatenates_per_voice_for_multipart_inputs():
  # Each input is a 2-voice Score; sequence should produce a 2-voice Score
  # where voice 0 = input1.voice0 + input2.voice0, voice 1 = same for v1.
  p1a = stream.Part(); p1a.append(bar(note.Note('C4', quarterLength=4), number=1))
  p1b = stream.Part(); p1b.append(bar(note.Note('E4', quarterLength=4), number=1))
  s1 = stream.Score(); s1.insert(0, p1a); s1.insert(0, p1b)

  p2a = stream.Part(); p2a.append(bar(note.Note('D4', quarterLength=4), number=1))
  p2b = stream.Part(); p2b.append(bar(note.Note('F4', quarterLength=4), number=1))
  s2 = stream.Score(); s2.insert(0, p2a); s2.insert(0, p2b)

  out = sequence(s1, s2)
  parts = list(out.getElementsByClass(stream.Part))
  assert len(parts) == 2
  for p in parts:
    measures = list(p.getElementsByClass(stream.Measure))
    assert [m.number for m in measures] == [1, 2]


def test_sequence_empty_returns_empty_score():
  s = sequence()
  assert isinstance(s, stream.Score)
  assert len(list(s.getElementsByClass(stream.Part))) == 0


def test_sequence_accepts_measures_directly():
  m1 = bar(note.Note('C4', quarterLength=4), number=1)
  m2 = bar(note.Note('D4', quarterLength=4), number=1)
  s = sequence(m1, m2)
  measures = list(s.getElementsByClass(stream.Part)[0]
                  .getElementsByClass(stream.Measure))
  assert [m.number for m in measures] == [1, 2]


def test_sequence_pads_missing_voices_with_rests():
  # Two inputs: input1 has one voice (4 bars), input2 has two voices (4 bars
  # each). The output should have two voices, both spanning the full 8 bars.
  # input1's missing voice 1 is padded with 4 rest measures.
  v1a = stream.Part(); v1a.append(bar(note.Note('C4', quarterLength=4), number=1))

  v2a = stream.Part(); v2a.append(bar(note.Note('D4', quarterLength=4), number=1))
  v2b = stream.Part(); v2b.append(bar(note.Note('E4', quarterLength=4), number=1))
  s2 = stream.Score(); s2.insert(0, v2a); s2.insert(0, v2b)

  out = sequence(v1a, s2)
  parts = list(out.getElementsByClass(stream.Part))
  assert len(parts) == 2

  # Both voices must span exactly 2 measures (input1's 1 + input2's 1).
  for p in parts:
    measures = list(p.getElementsByClass(stream.Measure))
    assert len(measures) == 2
    assert [m.number for m in measures] == [1, 2]

  # Voice 1 — the one missing from input1 — must have a rest in measure 1.
  voice_1_first_measure = list(parts[1].getElementsByClass(stream.Measure))[0]
  rests = [el for el in voice_1_first_measure.notesAndRests
           if isinstance(el, note.Rest)]
  assert len(rests) >= 1
  assert sum(r.duration.quarterLength for r in rests) == 4.0


def test_sequence_splits_different_instruments_at_same_voice_position():
  # A song-like case: chorus has [Piano, Vocalist], solo_chorus has
  # [Piano, ElectricGuitar]. Voice 0 (Piano in both) merges into one
  # continuous stave. Voice 1 differs (Vocalist vs ElectricGuitar) — must
  # split into two separate output staves with rests where inactive.
  def make_section(melody_inst, melody_pitch):
    p_harm = stream.Part(); p_harm.append(instrument.Piano())
    p_harm.append(bar(note.Note('C4', quarterLength=4), number=1))
    p_mel = stream.Part(); p_mel.append(melody_inst)
    p_mel.append(bar(note.Note(melody_pitch, quarterLength=4), number=1))
    sc = stream.Score(); sc.insert(0, p_harm); sc.insert(0, p_mel)
    return sc

  chorus = make_section(instrument.Vocalist(), 'E4')
  solo = make_section(instrument.ElectricGuitar(), 'G4')

  out = sequence(chorus, chorus, solo, chorus)
  parts = list(out.getElementsByClass(stream.Part))

  # Expect 3 staves: one Piano (continuous), one Vocalist (active in 3 of 4
  # sections, rests in the solo slot), one ElectricGuitar (active only in
  # the solo slot, rests in the other 3 sections).
  insts = [next(p.getElementsByClass(instrument.Instrument), None) for p in parts]
  inst_class_names = sorted(type(i).__name__ for i in insts if i is not None)
  assert inst_class_names == ['ElectricGuitar', 'Piano', 'Vocalist']

  # Every output stave must span all 4 bars (one bar per input section).
  for p in parts:
    measures = list(p.getElementsByClass(stream.Measure))
    assert len(measures) == 4

  # The ElectricGuitar stave must have rests in 3 of its 4 measures
  # (only active in the third position).
  eg_part = next(p for p, i in zip(parts, insts)
                 if i is not None and isinstance(i, instrument.ElectricGuitar))
  rest_measures = sum(
    1 for m in eg_part.getElementsByClass(stream.Measure)
    if any(isinstance(el, note.Rest) for el in m.notesAndRests)
    and not any(isinstance(el, note.Note) for el in m.notesAndRests)
  )
  assert rest_measures == 3

  # The Vocalist stave must have rests in 1 of its 4 measures
  # (silent during the solo).
  v_part = next(p for p, i in zip(parts, insts)
                if i is not None and isinstance(i, instrument.Vocalist))
  rest_measures_v = sum(
    1 for m in v_part.getElementsByClass(stream.Measure)
    if any(isinstance(el, note.Rest) for el in m.notesAndRests)
    and not any(isinstance(el, note.Note) for el in m.notesAndRests)
  )
  assert rest_measures_v == 1


def test_sequence_pad_uses_input_time_signature():
  # An input in 12/8 should produce 6.0-ql rest measures when its missing
  # voice is padded, not 4.0 (the default).
  v1a = stream.Part()
  v1a.append(bar(note.Rest(quarterLength=6), number=1,
                 time_signature=meter.TimeSignature('12/8')))

  v2a = stream.Part()
  v2a.append(bar(note.Note('C4', quarterLength=6), number=1,
                 time_signature=meter.TimeSignature('12/8')))
  v2b = stream.Part()
  v2b.append(bar(note.Note('E4', quarterLength=6), number=1,
                 time_signature=meter.TimeSignature('12/8')))
  s2 = stream.Score(); s2.insert(0, v2a); s2.insert(0, v2b)

  out = sequence(v1a, s2)
  parts = list(out.getElementsByClass(stream.Part))

  # Voice 1 — missing from input1 — has its measure 1 padded with a 6-ql rest.
  voice_1_first_measure = list(parts[1].getElementsByClass(stream.Measure))[0]
  rest_total = sum(r.duration.quarterLength
                   for r in voice_1_first_measure.notesAndRests
                   if isinstance(r, note.Rest))
  assert rest_total == 6.0


def test_sequence_first_padded_measure_carries_time_signature():
  """When an output stave starts with padded rest measures (because input 0
  doesn't contribute to that voice), the first measure must declare a
  TimeSignature. Without one, MusicXML emits a part with no leading <time>
  element and renderers fall back to 4/4, breaking the layout — even when
  later measures (carrying their own TimeSignature) do have notes."""
  # Two inputs: input1 has only voice 0 (in 12/8), input2 has voice 0 + 1.
  v1a = stream.Part()
  v1a.append(bar(note.Note('C4', quarterLength=6), number=1,
                 time_signature=meter.TimeSignature('12/8')))

  v2a = stream.Part()
  v2a.append(bar(note.Note('D4', quarterLength=6), number=1,
                 time_signature=meter.TimeSignature('12/8')))
  v2b = stream.Part()
  v2b.append(bar(note.Note('E4', quarterLength=6), number=1,
                 time_signature=meter.TimeSignature('12/8')))
  s2 = stream.Score(); s2.insert(0, v2a); s2.insert(0, v2b)

  out = sequence(v1a, s2)
  parts = list(out.getElementsByClass(stream.Part))
  voice_1_first_measure = list(parts[1].getElementsByClass(stream.Measure))[0]
  ts_in_first = next(
    (el for el in voice_1_first_measure if isinstance(el, meter.TimeSignature)),
    None,
  )
  assert ts_in_first is not None, "first padded measure must declare a TimeSignature"
  assert ts_in_first.ratioString == '12/8'


# ---------- repeat ----------

def test_repeat_concatenates_n_times():
  m = bar(note.Note('C4', quarterLength=4), number=1)
  s = repeat(m, 3)
  measures = list(s.getElementsByClass(stream.Part)[0]
                  .getElementsByClass(stream.Measure))
  assert len(measures) == 3
  assert [mm.number for mm in measures] == [1, 2, 3]


def test_repeat_zero_returns_empty():
  m = bar(note.Note('C4', quarterLength=4))
  s = repeat(m, 0)
  assert len(list(s.getElementsByClass(stream.Part))) == 0


def test_repeat_negative_raises():
  m = bar(note.Note('C4', quarterLength=4))
  with pytest.raises(ValueError, match="non-negative"):
    repeat(m, -1)


def test_repeat_does_not_alias_original():
  m = bar(note.Note('C4', quarterLength=4), number=1)
  s = repeat(m, 2)
  measures = list(s.getElementsByClass(stream.Part)[0]
                  .getElementsByClass(stream.Measure))
  # mutating one copy must not bleed into the other
  next(measures[0].notes).pitch.name = 'D'
  assert next(measures[1].notes).pitch.name == 'C'


# ---------- pentatonic ----------

def test_minor_pentatonic_e_one_octave():
  ps = minor_pentatonic('E', octave_range=(4, 4))
  names = [p.nameWithOctave for p in ps]
  # E minor pent: E, G, A, B, D — D wraps into octave 5 because it's above E4
  assert names == ['E4', 'G4', 'A4', 'B4', 'D5']


def test_major_pentatonic_c_one_octave():
  ps = major_pentatonic('C', octave_range=(4, 4))
  names = [p.name for p in ps]
  assert names == ['C', 'D', 'E', 'G', 'A']


def test_minor_pentatonic_accepts_key_object():
  k = key.Key('A', 'minor')
  ps = minor_pentatonic(k, octave_range=(4, 4))
  assert ps[0].name == 'A'


def test_major_pentatonic_accepts_key_object():
  """major_pentatonic accepts a Key just like the minor variant."""
  k = key.Key('G', 'major')
  ps = major_pentatonic(k, octave_range=(4, 4))
  assert ps[0].name == 'G'


def test_minor_pentatonic_includes_blue_note():
  ps_no_blue = minor_pentatonic('E', octave_range=(4, 4))
  ps_blue = minor_pentatonic('E', octave_range=(4, 4), include_blue=True)
  assert len(ps_blue) == len(ps_no_blue) + 1
  # b5 of E is Bb (or A#) — semitone 6 above E
  midis = [p.midi for p in ps_blue]
  assert (ps_no_blue[0].midi + 6) in midis


def test_major_pentatonic_has_no_include_blue_kwarg():
  """The blue note is a minor-pentatonic ornament, not a major-pentatonic
  one. Locking in the asymmetric kwarg surface."""
  with pytest.raises(TypeError, match="include_blue"):
    major_pentatonic('C', include_blue=True)  # type: ignore[call-arg]


def test_minor_pentatonic_spans_multiple_octaves():
  ps = minor_pentatonic('E', octave_range=(4, 5))
  midis = [p.midi for p in ps]
  assert midis == sorted(midis)
  # one octave has 5 notes; two octaves' worth should produce ~10 (some
  # may fall outside the range but we expect at least 9).
  assert len(ps) >= 9


def test_minor_pentatonic_inverted_octave_range_raises():
  with pytest.raises(ValueError, match="octave_range"):
    minor_pentatonic('C', octave_range=(5, 4))


def test_pentatonic_legacy_name_is_gone():
  """v0.3.3: `pentatonic` was renamed to `minor_pentatonic` +
  `major_pentatonic`. The legacy name must be unimportable so callers
  see an ImportError at module-load rather than a silent name shadowing."""
  from forge.music import lib as _lib
  assert not hasattr(_lib, 'pentatonic'), (
    "pentatonic should be removed entirely (no deprecation alias); "
    "callers must use minor_pentatonic or major_pentatonic"
  )


# ---------- executor injection ----------

def test_executor_injects_lib_into_snippet_namespace():
  from forge.core.executor import exec_python
  code = (
    "def compute(context):\n"
    "  m = bar(note.Note('C4', quarterLength=4))\n"
    "  return repeat(m, 2)\n"
  )
  _, result = exec_python(code, {})
  assert isinstance(result, stream.Score)
  measures = list(result.getElementsByClass(stream.Part)[0]
                  .getElementsByClass(stream.Measure))
  assert len(measures) == 2


# ---------- with_velocity (v0.3.6) ----------

def _make_notes(n):
  return [note.Note('C4', quarterLength=0.5) for _ in range(n)]


def test_with_velocity_uniform_int():
  ns = _make_notes(3)
  with_velocity(ns, 80)
  assert [n.volume.velocity for n in ns] == [80, 80, 80]


def test_with_velocity_cyclic_list():
  ns = _make_notes(5)
  with_velocity(ns, [100, 60])
  assert [n.volume.velocity for n in ns] == [100, 60, 100, 60, 100]


def test_with_velocity_human_profile_in_range():
  # 'human' = 75 + randint(-8, 8) ⇒ 67..83 inclusive.
  ns = _make_notes(20)
  with_velocity(ns, 'human')
  for n in ns:
    assert 67 <= n.volume.velocity <= 83, n.volume.velocity


def test_with_velocity_ghost_profile_in_range():
  # 'ghost' = 35 + randint(-5, 8) ⇒ 30..43 inclusive.
  ns = _make_notes(20)
  with_velocity(ns, 'ghost')
  for n in ns:
    assert 30 <= n.volume.velocity <= 43, n.volume.velocity


def test_with_velocity_accent_profile_in_range():
  # 'accent' = 110 + randint(-5, 10) ⇒ 105..120 inclusive.
  ns = _make_notes(20)
  with_velocity(ns, 'accent')
  for n in ns:
    assert 105 <= n.volume.velocity <= 120, n.volume.velocity


def test_with_velocity_crescendo_first_is_quiet_last_is_loud():
  ns = _make_notes(10)
  with_velocity(ns, 'crescendo')
  assert ns[0].volume.velocity <= 50
  assert ns[-1].volume.velocity >= 80


def test_with_velocity_decrescendo_first_is_loud_last_is_quiet():
  ns = _make_notes(10)
  with_velocity(ns, 'decrescendo')
  assert ns[0].volume.velocity >= 80
  assert ns[-1].volume.velocity <= 50


def test_with_velocity_skips_rests():
  ns = [note.Note('C4'), note.Rest(quarterLength=0.5), note.Note('C4')]
  with_velocity(ns, [100, 60])
  # rest is untouched; the two notes get 100 and 60 (positions 0 and 1
  # in the non-rest sequence).
  assert ns[0].volume.velocity == 100
  assert ns[2].volume.velocity == 60


def test_with_velocity_invalid_pattern_raises():
  with pytest.raises(ValueError, match="unknown velocity pattern"):
    with_velocity(_make_notes(1), 'unknown')


def test_with_velocity_empty_list_pattern_raises():
  with pytest.raises(ValueError, match="non-empty"):
    with_velocity(_make_notes(1), [])


def test_with_velocity_clamps_above_127():
  ns = _make_notes(1)
  with_velocity(ns, 200)
  assert ns[0].volume.velocity == 127


def test_with_velocity_clamps_below_1():
  ns = _make_notes(1)
  with_velocity(ns, -5)
  assert ns[0].volume.velocity == 1


# ---------- percussion factories (v0.3.6 Phase B + C) ----------

def test_closed_hihat_uses_gm_note_42():
  inst = closed_hihat()
  assert inst.percMapPitch == 42
  assert isinstance(inst, instrument.HiHatCymbal)


def test_open_hihat_uses_gm_note_46():
  inst = open_hihat()
  assert inst.percMapPitch == 46
  assert isinstance(inst, instrument.HiHatCymbal)


def test_pedal_hihat_uses_gm_note_44():
  inst = pedal_hihat()
  assert inst.percMapPitch == 44
  assert isinstance(inst, instrument.HiHatCymbal)


def test_all_hihat_factories_on_gm_channel_10():
  # music21 stores channel 0-indexed; channel 9 == GM channel 10.
  for fn in [closed_hihat, open_hihat, pedal_hihat]:
    assert fn().midiChannel == 9, fn.__name__


def test_low_tom_uses_gm_note_41():
  inst = low_tom()
  assert inst.percMapPitch == 41
  assert isinstance(inst, instrument.TomTom)


def test_mid_tom_uses_gm_note_47():
  inst = mid_tom()
  assert inst.percMapPitch == 47


def test_high_tom_uses_gm_note_50():
  inst = high_tom()
  assert inst.percMapPitch == 50


def test_crash_cymbal_uses_gm_note_49():
  inst = crash_cymbal()
  assert inst.percMapPitch == 49
  assert isinstance(inst, instrument.CrashCymbals)


def test_ride_cymbal_uses_gm_note_51():
  inst = ride_cymbal()
  assert inst.percMapPitch == 51
  assert isinstance(inst, instrument.RideCymbals)


def test_all_kit_factories_on_gm_channel_10():
  for fn in [closed_hihat, open_hihat, pedal_hihat,
             low_tom, mid_tom, high_tom,
             crash_cymbal, ride_cymbal]:
    assert fn().midiChannel == 9, fn.__name__


# ---------- v0.3.7: percussion serialization fix for MuseScore ----------
# music21's MusicXML exporter enforces channel uniqueness per Score
# (m21ToXml.py:2801-2810). The first percussion instrument keeps
# midiChannel=9; subsequent same-channel parts get reassigned to
# melodic channels 1, 2, 3... — which MuseScore renders as Piano
# treble staves. The v0.3.7 factories patch autoAssignMidiChannel
# to return 9 unconditionally; tests verify the post-fix MusicXML
# output puts every percussion part on channel 10.

def _serialize_to_text(score):
  from music21 import musicxml
  xml = musicxml.m21ToXml.GeneralObjectExporter(score).parse()
  return xml.decode('utf-8') if isinstance(xml, bytes) else str(xml)


def _make_multi_perc_score(factories):
  """Build a Score with one Part per factory call. Returns the Score
  and the MusicXML text."""
  import re
  score = stream.Score()
  for fn in factories:
    p = stream.Part()
    p.append(fn())
    p.append(note.Note('C4', quarterLength=1))
    score.insert(0, p)
  text = _serialize_to_text(score)
  channels = re.findall(r'<midi-channel>(\d+)</midi-channel>', text)
  names = re.findall(r'<instrument-name[^>]*>([^<]+)</instrument-name>', text)
  return score, text, channels, names


def test_kick_factory_returns_BassDrum_with_kick_name():
  inst = kick()
  assert isinstance(inst, instrument.BassDrum)
  assert inst.instrumentName == 'Kick'
  assert inst.midiChannel == 9


def test_snare_factory_returns_SnareDrum_with_snare_name():
  inst = snare()
  assert isinstance(inst, instrument.SnareDrum)
  assert inst.instrumentName == 'Snare'
  assert inst.midiChannel == 9


def test_multi_percussion_score_all_channels_are_10():
  """Regression test for v0.2.34's MuseScore rendering bug. Pre-fix:
  music21 assigned ch10 only to the first percussion part; the rest
  got melodic channels (1, 2, 3...). Post-fix: every percussion part
  serializes to <midi-channel>10</midi-channel>."""
  _score, _text, channels, _names = _make_multi_perc_score([
    kick, snare, closed_hihat, open_hihat, low_tom, mid_tom, crash_cymbal,
  ])
  assert channels == ['10'] * 7, (
    f"all percussion parts should be on GM channel 10; got {channels}"
  )


def test_kit_factory_instrument_names_are_kit_conventional():
  """No 'Bangu' (music21's default for BassDrum) or 'Hi-Hat Cymbal'
  / 'Tom-Tom' bare class names. Each factory overrides to a
  kit-conventional label."""
  _score, _text, _channels, names = _make_multi_perc_score([
    kick, snare, closed_hihat, open_hihat, pedal_hihat,
    low_tom, mid_tom, high_tom, crash_cymbal, ride_cymbal,
  ])
  expected = [
    'Kick', 'Snare', 'Closed Hi-Hat', 'Open Hi-Hat', 'Pedal Hi-Hat',
    'Low Tom', 'Mid Tom', 'High Tom', 'Crash Cymbal', 'Ride Cymbal',
  ]
  assert names == expected, f"expected {expected}, got {names}"
  # Hard guard against the v0.2.34 'Bangu Bass drum' issue.
  for n in names:
    assert 'Bangu' not in n, f"name {n!r} contains 'Bangu'"


def test_force_perc_channel_does_not_change_percMapPitch():
  """percMapPitch values must stay unchanged from v0.3.6 — MIDI export
  (GarageBand-readable) was already correct. The v0.3.7 fix only
  touches autoAssignMidiChannel + instrumentName."""
  assert closed_hihat().percMapPitch == 42
  assert open_hihat().percMapPitch == 46
  assert pedal_hihat().percMapPitch == 44
  assert low_tom().percMapPitch == 41
  assert mid_tom().percMapPitch == 47
  assert high_tom().percMapPitch == 50
  assert crash_cymbal().percMapPitch == 49
  assert ride_cymbal().percMapPitch == 51
