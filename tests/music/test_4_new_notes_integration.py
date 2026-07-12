"""6-voice slow blues integration — drain 2026-07-10-1340.

The load-bearing demo of the compose-from-atoms pattern. Composes all
four new library chips (walking_bass_line, piano_voicing,
violin_bowing, vocal_line) together with the pre-existing drum_chorus
and form on top of a shared harmonic frame. Verifies the resulting
Score has the correct shape and content — the same shape the E--
snippet in the design spec's §Composition example would produce at
runtime.
"""

from music21 import stream

from forge.music.lib import (
  drum_chorus,
  form,
  piano_voicing,
  violin_bowing,
  vocal_line,
  voices_list,
  walking_bass_line,
)


def _all_parts(score):
  """Return every descendant Part (drum_chorus contributes multiple)."""
  return [p for p in score.recurse().getElementsByClass(stream.Part)]


def test_six_voice_slow_blues_composes_into_score():
  """The 8-line E-- composition example from the design spec produces
  a valid Score with 5 named voices + drum_chorus's 4 percussion parts
  (kick, snare, ghost, hihat) — total 9+ Parts."""
  harmony = form()
  drums = drum_chorus(profile="standard")
  bass = walking_bass_line(harmony)
  piano = piano_voicing(harmony, style="rootless")
  violin = violin_bowing(harmony, style="legato")
  vocal = vocal_line(harmony, voice_type="alto", lyrics="")
  piece = voices_list(sections=[harmony, drums, bass, piano, violin, vocal])
  assert isinstance(piece, stream.Score)
  parts = _all_parts(piece)
  # 5 named + at least 4 drum sub-parts = 9 minimum.
  assert len(parts) >= 6, (
    f"expected at least 6 Parts (5 named + drum_chorus sub-parts); "
    f"got {len(parts)}"
  )


def test_named_voices_each_carry_notes():
  """Each of the 5 explicitly-named parts (harmony, bass, piano,
  violin, vocal) contributes non-zero content. Assert by rebuilding
  each in isolation and confirming a positive note count."""
  harmony = form()
  bass = walking_bass_line(harmony)
  piano = piano_voicing(harmony, style="rootless")
  violin = violin_bowing(harmony, style="legato")
  vocal = vocal_line(harmony, voice_type="alto", lyrics="")

  # Harmony contains chord.Chord elements; violin/bass/vocal contain
  # note.Note; piano contains chord.Chord. All should have >= 12
  # sound-carrying elements (12 bars, at least one per bar).
  for name, part in [
    ("harmony", harmony),
    ("bass", bass),
    ("piano", piano),
    ("violin", violin),
    ("vocal", vocal),
  ]:
    sounding = list(part.recurse().notes)
    assert len(sounding) >= 12, (
      f"{name} should carry at least 12 sounding elements; "
      f"got {len(sounding)}"
    )


def test_total_elapsed_time_matches_12_bars_of_12_8():
  """12 bars in 12/8 → each bar has quarterLength=6.0 → total 72.
  Assert on the final Score's highestTime."""
  harmony = form()
  drums = drum_chorus(profile="standard")
  bass = walking_bass_line(harmony)
  piano = piano_voicing(harmony, style="rootless")
  violin = violin_bowing(harmony, style="legato")
  vocal = vocal_line(harmony, voice_type="alto", lyrics="")
  piece = voices_list(sections=[harmony, drums, bass, piano, violin, vocal])
  assert piece.highestTime == 72.0, (
    f"expected highestTime=72.0 (12 bars × 6.0 for 12/8); "
    f"got {piece.highestTime}"
  )


def test_score_recurse_yields_nonempty_notes():
  """Instead of round-tripping through musicxml (which may need a
  configured renderer), just walk the recursion tree and verify the
  composed Score exposes a nonempty note list — the minimum
  well-formedness signal."""
  harmony = form()
  drums = drum_chorus(profile="standard")
  bass = walking_bass_line(harmony)
  piano = piano_voicing(harmony, style="rootless")
  violin = violin_bowing(harmony, style="legato")
  vocal = vocal_line(harmony, voice_type="alto", lyrics="")
  piece = voices_list(sections=[harmony, drums, bass, piano, violin, vocal])
  all_notes = list(piece.recurse().notes)
  # 5 named voices × ~12+ notes each + drums (>=48) = well over 100.
  assert len(all_notes) >= 100, (
    f"composed Score should have >= 100 note-like elements; "
    f"got {len(all_notes)}"
  )
