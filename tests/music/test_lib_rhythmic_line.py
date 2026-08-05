"""Tests for `forge.music.lib.rhythmic_line`.

CW-forge-music-lib-add-rhythmic-line-tier-1 (drain 2026-08-05-0730).

First Tier-1 composition primitive. The rejection tests carry most of
the weight: a duration typo that silently became a default would change
the music without saying so, and the author would have no way to tell
the difference between what they asked for and what they got.
"""
import pytest

from forge.music import lib

music21 = pytest.importorskip("music21")


def shape(stream_obj):
  """(kind, quarterLength) per element, in order."""
  return [(type(e).__name__, e.quarterLength) for e in stream_obj.notesAndRests]


class TestDurations:
  def test_floats_are_quarter_note_units(self):
    assert shape(lib.rhythmic_line([1.0, 1.0, 2.0])) == [
      ("Note", 1.0), ("Note", 1.0), ("Note", 2.0),
    ]

  def test_shorthand_matches_its_float_equivalent(self):
    # The pairing IS the contract — if these ever diverge, one of the
    # two spellings is lying to whoever used it.
    assert shape(lib.rhythmic_line(["q", "e", "e", "h"])) == \
           shape(lib.rhythmic_line([1.0, 0.5, 0.5, 2.0]))

  def test_every_shorthand_resolves(self):
    for name in lib._RHYTHM_SHORTHAND:
      assert shape(lib.rhythmic_line([name])) == [("Note", lib._RHYTHM_SHORTHAND[name])]

  def test_dotted_values_are_one_and_a_half_times_the_plain_value(self):
    assert lib._RHYTHM_SHORTHAND["dq"] == lib._RHYTHM_SHORTHAND["q"] * 1.5
    assert lib._RHYTHM_SHORTHAND["de"] == lib._RHYTHM_SHORTHAND["e"] * 1.5

  def test_shorthand_is_case_and_whitespace_insensitive(self):
    assert shape(lib.rhythmic_line([" Q ", "E"])) == shape(lib.rhythmic_line(["q", "e"]))


class TestRests:
  def test_r_suffix_makes_a_rest(self):
    assert shape(lib.rhythmic_line(["q", "qr", "q"])) == [
      ("Note", 1.0), ("Rest", 1.0), ("Note", 1.0),
    ]

  def test_negative_float_makes_a_rest_of_that_length(self):
    assert shape(lib.rhythmic_line([1.0, -1.0])) == [("Note", 1.0), ("Rest", 1.0)]

  def test_every_shorthand_has_a_working_rest_form(self):
    # The rest spellings are derived, not listed, so this is what keeps
    # a newly-added duration from shipping without its rest form.
    for name, length in lib._RHYTHM_SHORTHAND.items():
      assert shape(lib.rhythmic_line([name + "r"])) == [("Rest", length)]


class TestPitchAndTempo:
  def test_default_pitch_is_middle_c(self):
    assert [n.nameWithOctave for n in lib.rhythmic_line(["q"]).notes] == ["C4"]

  def test_pitch_applies_to_every_note(self):
    assert [n.nameWithOctave for n in lib.rhythmic_line(["q"] * 3, pitch="D4").notes] == \
           ["D4", "D4", "D4"]

  def test_tempo_mark_lands_at_offset_zero(self):
    marks = lib.rhythmic_line(["q"], tempo=90).metronomeMarkBoundaries()
    assert marks[0][2].number == 90

  def test_default_tempo_is_120(self):
    marks = lib.rhythmic_line(["q"]).metronomeMarkBoundaries()
    assert marks[0][2].number == 120


class TestRejections:
  def test_empty_pattern(self):
    with pytest.raises(ValueError, match="pattern is empty"):
      lib.rhythmic_line([])

  def test_unknown_shorthand_names_the_position_and_the_alternatives(self):
    with pytest.raises(ValueError) as exc:
      lib.rhythmic_line(["q", "zz"])
    msg = str(exc.value)
    assert "position 1" in msg          # which element, not just that one is bad
    assert "'zz'" in msg                 # what they actually wrote
    assert "q" in msg                    # what they could have written

  def test_zero_duration(self):
    with pytest.raises(ValueError, match="zero duration"):
      lib.rhythmic_line([1.0, 0])

  def test_non_numeric_non_string(self):
    with pytest.raises(ValueError, match=r"pattern\[0\]"):
      lib.rhythmic_line([None])

  def test_bare_r_is_not_a_rest(self):
    # "r" alone has no duration to rest for; accepting it would mean
    # guessing one.
    with pytest.raises(ValueError, match="unknown duration"):
      lib.rhythmic_line(["r"])

  @pytest.mark.parametrize("bad", [0, -1, 1.5, "120", True])
  def test_tempo_must_be_a_positive_int(self, bad):
    # True is included deliberately: bool is an int subclass, so a
    # `tempo=True` typo would otherwise be accepted as 1 BPM.
    with pytest.raises(ValueError, match="tempo must be"):
      lib.rhythmic_line(["q"], tempo=bad)


def test_registered_in_both_executor_chip_lists():
  """Shipping the function without registering it is exactly what drain
  2026-08-05-0620 spent a whole investigation on.

  Compares by qualname, not identity: `test_lib_deferred_music21_import`
  reloads `forge.music.lib` to exercise the late-mount path, so by the
  time the full suite reaches here the module object may not be the one
  the executor captured. Identity would fail for a reason that has
  nothing to do with whether the chip is registered — and did, on the
  first full-suite run of this drain.
  """
  from forge.core import executor
  registered = executor._FORGE_MUSIC_LIB_NAMES["rhythmic_line"]
  assert registered.__qualname__ == "rhythmic_line"
  # The executor's import-time guard requires both lists agree; assert
  # the lazy one explicitly so a future edit to only the eager dict
  # fails here with a clear message rather than at import.
  assert "rhythmic_line" in executor._MUSIC_LAZY_CHIP_NAMES
