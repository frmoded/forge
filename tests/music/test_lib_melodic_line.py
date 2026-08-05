"""Tests for `forge.music.lib.melodic_line`.

CW-forge-music-lib-add-melodic-line-tier-1 (drain 2026-08-05-1100).

Second Tier-1 composition primitive. Two things carry the weight here
that `rhythmic_line`'s tests did not have to:

  1. The two functions now SHARE their duration parse. The tests that
     assert agreement between them are the ones that would catch a
     future edit to one path that forgot the other.
  2. Pitch is a new failure surface. music21 raises for a bad pitch on
     its own, but its message names its parser rather than the argument
     the author wrote, so the wrapping is the feature and is tested as
     one.
"""
import pytest

from forge.music import lib

music21 = pytest.importorskip("music21")


def shape(stream_obj):
  """(kind, quarterLength) per element, in order."""
  return [(type(e).__name__, e.quarterLength) for e in stream_obj.notesAndRests]


def pitches_of(stream_obj):
  return [n.nameWithOctave for n in stream_obj.notes]


class TestSharedDurationParse:
  """`melodic_line` must accept exactly what `rhythmic_line` accepts.

  Not a nice-to-have: the drain said do not duplicate the shorthand,
  and the reason is that two copies drift silently — both keep
  "working", they just disagree about what a duration means.
  """

  def test_every_shorthand_resolves_identically_in_both(self):
    for name, length in lib._RHYTHM_SHORTHAND.items():
      assert shape(lib.melodic_line([name], ["C4"])) == \
             shape(lib.rhythmic_line([name])) == [("Note", length)]

  def test_every_rest_form_resolves_identically_in_both(self):
    for name, length in lib._RHYTHM_SHORTHAND.items():
      assert shape(lib.melodic_line([name + "r"], ["C4"])) == \
             shape(lib.rhythmic_line([name + "r"])) == [("Rest", length)]

  def test_floats_are_quarter_note_units(self):
    assert shape(lib.melodic_line([1.0, 0.5, 2.0], ["C4", "D4", "E4"])) == [
      ("Note", 1.0), ("Note", 0.5), ("Note", 2.0),
    ]

  def test_negative_float_is_a_rest_in_both(self):
    assert shape(lib.melodic_line([1.0, -1.0], ["C4", "C4"])) == \
           shape(lib.rhythmic_line([1.0, -1.0]))

  def test_shorthand_is_case_and_whitespace_insensitive(self):
    assert shape(lib.melodic_line([" Q ", "E"], ["C4", "D4"])) == \
           shape(lib.melodic_line(["q", "e"], ["C4", "D4"]))

  def test_duration_errors_name_melodic_line_not_rhythmic_line(self):
    # The parse is shared; the message must still name the function the
    # author actually called, or the traceback sends them to the wrong
    # docstring.
    with pytest.raises(ValueError, match="melodic_line: unknown duration"):
      lib.melodic_line(["zz"], ["C4"])
    with pytest.raises(ValueError, match="rhythmic_line: unknown duration"):
      lib.rhythmic_line(["zz"])


class TestPitches:
  def test_pitches_land_in_order(self):
    assert pitches_of(lib.melodic_line(
      [1.0] * 4, ["C4", "D4", "E4", "F4"]
    )) == ["C4", "D4", "E4", "F4"]

  def test_accidentals(self):
    assert pitches_of(lib.melodic_line([1.0, 1.0], ["D#4", "B-3"])) == \
           ["D#4", "B-3"]

  def test_midi_numbers(self):
    assert pitches_of(lib.melodic_line([1.0, 1.0], [60, 67])) == ["C4", "G4"]

  def test_names_and_midi_can_be_mixed(self):
    assert pitches_of(lib.melodic_line([1.0, 1.0], ["C4", 67])) == ["C4", "G4"]

  def test_whitespace_around_a_name_is_tolerated(self):
    assert pitches_of(lib.melodic_line([1.0], [" C4 "])) == ["C4"]


class TestRestsIgnoreTheirPitch:
  def test_rest_pitch_is_not_sounded(self):
    s = lib.melodic_line(["q", "qr", "q"], ["C4", "D4", "G4"])
    assert shape(s) == [("Note", 1.0), ("Rest", 1.0), ("Note", 1.0)]
    # D4 was the rest's placeholder — it must not appear as a note.
    assert pitches_of(s) == ["C4", "G4"]

  def test_a_rests_placeholder_is_not_validated(self):
    """Documented contract: for a rest the pitch is IGNORED.

    "Ignored" has to mean ignored, not "ignored unless it happens to be
    unparseable" — otherwise an author who writes a filler like "-" or
    "" gets an error about a pitch that was never going to sound.
    """
    assert shape(lib.melodic_line(["qr"], ["not-a-pitch"])) == [("Rest", 1.0)]
    assert shape(lib.melodic_line([-1.0], [None])) == [("Rest", 1.0)]


class TestTempo:
  def test_default_tempo_is_120(self):
    marks = lib.melodic_line([1.0], ["C4"]).metronomeMarkBoundaries()
    assert marks[0][2].number == 120

  def test_tempo_mark_lands_at_offset_zero(self):
    marks = lib.melodic_line([1.0], ["C4"], tempo=90).metronomeMarkBoundaries()
    assert marks[0][0] == 0.0
    assert marks[0][2].number == 90

  @pytest.mark.parametrize("bad", [0, -1, 1.5, "120", True])
  def test_tempo_must_be_a_positive_int(self, bad):
    # True included deliberately: bool is an int subclass, so a
    # `tempo=True` typo would otherwise be accepted as 1 BPM.
    with pytest.raises(ValueError, match="melodic_line: tempo must be"):
      lib.melodic_line([1.0], ["C4"], tempo=bad)


class TestLengthAgreement:
  def test_mismatch_names_both_lengths(self):
    with pytest.raises(ValueError) as exc:
      lib.melodic_line([1.0, 1.0, 1.0], ["C4", "D4"])
    msg = str(exc.value)
    assert "3 elements" in msg   # what they wrote
    assert "has 2" in msg        # what it has to match

  def test_mismatch_is_rejected_in_both_directions(self):
    with pytest.raises(ValueError, match="same length"):
      lib.melodic_line([1.0], ["C4", "D4"])

  def test_empty_pattern(self):
    with pytest.raises(ValueError, match="melodic_line: pattern is empty"):
      lib.melodic_line([], ["C4"])

  def test_empty_pitches(self):
    with pytest.raises(ValueError, match="melodic_line: pitches is empty"):
      lib.melodic_line([1.0], [])

  def test_both_empty_reports_pattern_first(self):
    # Two things are wrong; report the one the author most likely meant
    # to fill in rather than making them fix errors in sequence.
    with pytest.raises(ValueError, match="pattern is empty"):
      lib.melodic_line([], [])


class TestPitchRejections:
  def test_unreadable_name_names_the_position_and_the_value(self):
    with pytest.raises(ValueError) as exc:
      lib.melodic_line([1.0, 1.0], ["C4", "H9"])
    msg = str(exc.value)
    assert "pitches[1]" in msg     # which element
    assert "'H9'" in msg           # what they wrote
    assert "C4" in msg             # what they could have written

  @pytest.mark.parametrize("bad", [128, -1, 200])
  def test_midi_out_of_range(self, bad):
    with pytest.raises(ValueError, match="outside 0-127"):
      lib.melodic_line([1.0], [bad])

  def test_midi_boundaries_are_inclusive(self):
    assert len(lib.melodic_line([1.0, 1.0], [0, 127]).notes) == 2

  def test_bool_is_not_midi_1(self):
    # Same trap as tempo: bool subclasses int, so `True` would be a
    # silently-accepted MIDI 1 rather than an obvious mistake.
    with pytest.raises(ValueError, match=r"pitches\[0\] is True"):
      lib.melodic_line([1.0], [True])

  @pytest.mark.parametrize("bad", [None, "", "   ", 3.5, []])
  def test_non_pitch_values(self, bad):
    with pytest.raises(ValueError, match=r"pitches\[0\]"):
      lib.melodic_line([1.0], [bad])

  def test_error_arrives_before_a_half_built_stream(self):
    """Validation is eager, per element, in order.

    A late pitch failure after early notes were appended would leave the
    author guessing whether anything was written.
    """
    with pytest.raises(ValueError, match=r"pitches\[2\]"):
      lib.melodic_line([1.0] * 4, ["C4", "D4", "H9", "F4"])


def test_registered_in_both_executor_chip_lists():
  """Per drain 2026-08-05-0620 and the lesson `rhythmic_line` learned:
  shipping the function without registering it in BOTH lists is the
  failure mode, and only one of the two fails loudly.

  Compares by qualname, not identity — `test_lib_deferred_music21_import`
  reloads `forge.music.lib`, so by the time the full suite reaches here
  the module object may not be the one the executor captured.
  """
  from forge.core import executor
  assert executor._FORGE_MUSIC_LIB_NAMES["melodic_line"].__qualname__ == \
         "melodic_line"
  assert "melodic_line" in executor._MUSIC_LAZY_CHIP_NAMES
