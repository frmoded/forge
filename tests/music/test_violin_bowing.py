"""Tests for violin_bowing — drain 2026-07-10-1340 phase 3.

Verifies the pinned invariants per D-note-2:
- Returns music21.stream.Part with a Violin instrument first.
- Style enum: legato | detache | marcato | portato; matching
  articulations/spanners are attached (music21 has no
  articulations.Slur, so legato uses spanner.Slur — documented in
  the chip's docstring).
- Register enum: d4_a5 (D4-A5) | g3_e6 (G3-E6).
- Dynamic mark emitted at measure 1 offset 0.
- Literal `melody=` parameter takes over from the deterministic
  chord-tone walker.
- Invalid style / dynamic / register raise ValueError.
"""

import pytest
from music21 import (
  articulations, dynamics, instrument, spanner, stream,
)

from forge.music.lib import form, violin_bowing


def _all_notes(part):
  return list(part.recurse().notes)


def test_returns_part_with_violin():
  h = form()
  vb = violin_bowing(h)
  assert isinstance(vb, stream.Part)
  insts = list(vb.getElementsByClass(instrument.Instrument))
  assert insts and isinstance(insts[0], instrument.Violin), (
    f"expected Violin; got {type(insts[0]).__name__ if insts else 'none'}"
  )


def test_default_walker_notes_in_d4_a5_range():
  """Register `d4_a5` — MIDI 62 (D4) to 81 (A5) inclusive."""
  h = form()
  vb = violin_bowing(h)  # default register d4_a5
  midis = [n.pitch.midi for n in _all_notes(vb)]
  assert min(midis) >= 62 and max(midis) <= 81, (
    f"d4_a5 register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [62, 81]"
  )


def test_g3_e6_register_bounds():
  """Register `g3_e6` — MIDI 55 (G3) to 88 (E6). Wider than d4_a5;
  still bounded on both ends."""
  h = form()
  vb = violin_bowing(h, register="g3_e6")
  midis = [n.pitch.midi for n in _all_notes(vb)]
  assert min(midis) >= 55 and max(midis) <= 88, (
    f"g3_e6 register violated: midi range {min(midis)}-{max(midis)} "
    f"outside [55, 88]"
  )


def test_four_notes_per_bar_at_correct_duration():
  """Four notes per bar at ql=bar_ql/4. In 12/8 (bar_ql=6): ql=1.5."""
  h = form()  # 12/8
  vb = violin_bowing(h)
  for m in vb.getElementsByClass(stream.Measure):
    ns = list(m.notes)
    assert len(ns) == 4, (
      f"bar {m.number}: expected 4 notes; got {len(ns)}"
    )
    for n in ns:
      assert n.duration.quarterLength == 1.5, (
        f"bar {m.number}: expected ql=1.5 (dotted quarter); "
        f"got {n.duration.quarterLength}"
      )


def test_legato_style_emits_slur_spanners():
  """Legato: one Slur per measure spanning that bar's notes.

  music21 has `spanner.Slur` but no `articulations.Slur` — the chip
  uses the Spanner form; this test verifies at least one Slur is
  present on the part."""
  h = form()
  vb = violin_bowing(h, style="legato")
  slurs = list(vb.recurse().getElementsByClass(spanner.Slur))
  assert slurs, (
    f"legato should emit at least one spanner.Slur; got 0"
  )


def test_marcato_style_adds_accent_articulations():
  h = form()
  vb = violin_bowing(h, style="marcato")
  accents = 0
  for n in _all_notes(vb):
    for a in n.articulations:
      if isinstance(a, articulations.Accent):
        accents += 1
  # 12 bars × 4 notes = 48 notes; each gets an Accent.
  assert accents >= 48, (
    f"marcato should tag every note with an Accent; got {accents}"
  )


def test_portato_style_adds_staccato_and_tenuto():
  h = form()
  vb = violin_bowing(h, style="portato")
  stacs = tens = 0
  for n in _all_notes(vb):
    for a in n.articulations:
      if isinstance(a, articulations.Staccato):
        stacs += 1
      elif isinstance(a, articulations.Tenuto):
        tens += 1
  assert stacs >= 48 and tens >= 48, (
    f"portato should tag every note with staccato + tenuto; "
    f"got {stacs} staccatos, {tens} tenutos"
  )


def test_detache_style_adds_no_articulations_and_no_slurs():
  """Detache is the default note-by-note bowing — no articulations,
  no slurs."""
  h = form()
  vb = violin_bowing(h, style="detache")
  arts = sum(len(n.articulations) for n in _all_notes(vb))
  slurs = list(vb.recurse().getElementsByClass(spanner.Slur))
  assert arts == 0, f"detache should add no articulations; got {arts}"
  assert not slurs, f"detache should add no slurs; got {len(slurs)}"


def test_literal_melody_uses_provided_pitches():
  """Non-empty `melody=` overrides the walker with a whitespace-split
  pitch list, cycled across bars. Provided pitches may still be
  register-fit — pitch class must match input for at least the first
  few notes."""
  h = form()
  vb = violin_bowing(h, melody="E5 G5 A5 B4", register="g3_e6")
  notes = _all_notes(vb)
  # The first bar's four notes should have the pitch classes E, G, A, B
  # in order (register-fit does not change pitch class).
  assert [n.pitch.name for n in notes[:4]] == ["E", "G", "A", "B"], (
    f"literal melody first-bar pitch classes should be E G A B; "
    f"got {[n.pitch.name for n in notes[:4]]}"
  )


def test_dynamic_mark_present_in_first_measure():
  h = form()
  vb = violin_bowing(h, dynamic="mf")
  measures = list(vb.getElementsByClass(stream.Measure))
  assert measures, "expected at least one measure"
  dyns = list(measures[0].getElementsByClass(dynamics.Dynamic))
  assert dyns, "first measure should carry a Dynamic mark"
  assert dyns[0].value == "mf", (
    f"expected 'mf'; got {dyns[0].value!r}"
  )


def test_invalid_style_raises():
  h = form()
  with pytest.raises(ValueError, match="style"):
    violin_bowing(h, style="pizzicato")


def test_invalid_dynamic_raises():
  h = form()
  with pytest.raises(ValueError, match="dynamic"):
    violin_bowing(h, dynamic="fff")  # not in enum


def test_invalid_register_raises():
  h = form()
  with pytest.raises(ValueError, match="register"):
    violin_bowing(h, register="c4_g5")


def test_invalid_melody_token_raises():
  """A garbage melody token raises ValueError with a helpful message."""
  h = form()
  with pytest.raises(ValueError, match="melody"):
    violin_bowing(h, melody="not_a_pitch")
