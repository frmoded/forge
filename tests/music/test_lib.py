import pytest
from music21 import key, meter, note, pitch, stream, instrument

from forge.music.lib import bar, voices, sequence, repeat, pentatonic


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

def test_pentatonic_minor_e_one_octave():
  ps = pentatonic('E', mode='minor', octave_range=(4, 4))
  names = [p.nameWithOctave for p in ps]
  # E minor pent: E, G, A, B, D — D wraps into octave 5 because it's above E4
  assert names == ['E4', 'G4', 'A4', 'B4', 'D5']


def test_pentatonic_major_c_one_octave():
  ps = pentatonic('C', mode='major', octave_range=(4, 4))
  names = [p.name for p in ps]
  assert names == ['C', 'D', 'E', 'G', 'A']


def test_pentatonic_accepts_key_object():
  k = key.Key('A', 'minor')
  ps = pentatonic(k, mode='minor', octave_range=(4, 4))
  assert ps[0].name == 'A'


def test_pentatonic_includes_blue_note():
  ps_no_blue = pentatonic('E', mode='minor', octave_range=(4, 4))
  ps_blue = pentatonic('E', mode='minor', octave_range=(4, 4), include_blue=True)
  assert len(ps_blue) == len(ps_no_blue) + 1
  # b5 of E is Bb (or A#) — semitone 6 above E
  midis = [p.midi for p in ps_blue]
  assert (ps_no_blue[0].midi + 6) in midis


def test_pentatonic_spans_multiple_octaves():
  ps = pentatonic('E', mode='minor', octave_range=(4, 5))
  midis = [p.midi for p in ps]
  assert midis == sorted(midis)
  # one octave has 5 notes; two octaves' worth should produce ~10 (some
  # may fall outside the range but we expect at least 9).
  assert len(ps) >= 9


def test_pentatonic_invalid_mode_raises():
  with pytest.raises(ValueError, match="mode"):
    pentatonic('C', mode='dorian')


def test_pentatonic_inverted_octave_range_raises():
  with pytest.raises(ValueError, match="octave_range"):
    pentatonic('C', octave_range=(5, 4))


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
