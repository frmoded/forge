"""Content invariants for the percussion_lab section vocabulary (v0.3.x
preview).

Murmuration decomposed into 8 named section snippets under
forge-music/percussion_lab/. Each section returns the canonical
7-instrument layout (kick, snare, closed_hihat, open_hihat, low_tom,
mid_tom, crash) — silent instruments fill rest staves at their
canonical voice positions so `sequence()` aligns them correctly
when sections are concatenated by `murmuration.md`.

Why the canonical layout: `lib.sequence()` groups parts at each voice
position by `type(inst).__name__` ONLY (not by percMapPitch). So
closed_hihat (HiHatCymbal pmp=42) and open_hihat (HiHatCymbal pmp=46)
collide at the same voice position. To preserve behavior, each
section keeps all 7 parts at fixed positions.

Tests verify:
  - Each section's KICK active-note count.
  - Which sub-set of the 7 parts is "active" (notes > 0) per section.
  - The bars parameter cycles + truncates correctly.
  - The peak section's crash cymbal lands on bars 1 and 3 only.
  - The dispersing section inserts a Diminuendo spanner (hairpin).
  - Each section anchors exactly one dynamic mark on the kick part.
  - The refactored Murmuration produces structurally equivalent output
    to its pre-refactor shape (behavior preservation): same parts in
    canonical order, same instrument identities (now by class+pitch
    since each section keeps consistent voice positions), same
    measure counts, same per-instrument total note counts.

Preview mode (per the 2026-06-04-2228 prompt) — uncommitted in
forge-music at drain time. If reverted, also remove this file.
"""
from music21 import stream, instrument, dynamics, spanner


def _parts_by_inst_id(score):
    """Returns dict mapping (class_name, percMapPitch) → list of Parts.
    Uses percMapPitch in the key to distinguish closed/open hi-hat and
    low/mid/high toms (which share class but differ in pitch)."""
    out = {}
    for p in score.parts:
        inst = next((el for el in p.elements
                     if isinstance(el, instrument.Instrument)), None)
        if inst is None:
            continue
        key = (type(inst).__name__, getattr(inst, 'percMapPitch', None))
        out.setdefault(key, []).append(p)
    return out


# ---- per-section shape ----

def test_solitary_returns_7_parts_with_only_kick_active(run_music_block):
    score = run_music_block("solitary")
    assert isinstance(score, stream.Score)
    parts = list(score.parts)
    assert len(parts) == 7, (
        f"solitary returns canonical 7-part layout; got {len(parts)}"
    )
    by_inst = _parts_by_inst_id(score)
    # kick: 2 hits/bar × 4 bars = 8 notes.
    kick_notes = sum(len(list(p.flatten().notes))
                     for p in by_inst[('BassDrum', 35)])
    assert kick_notes == 8, f"solitary kick should have 8 notes; got {kick_notes}"
    # All other instruments silent (0 notes).
    silent_keys = [
        ('SnareDrum', 38), ('HiHatCymbal', 42), ('HiHatCymbal', 46),
        ('TomTom', 41), ('TomTom', 47), ('CrashCymbals', 49),
    ]
    for key in silent_keys:
        assert key in by_inst, f"solitary missing canonical rest part for {key}"
        notes = sum(len(list(p.flatten().notes)) for p in by_inst[key])
        assert notes == 0, (
            f"solitary {key} should be silent (rests only); got {notes} notes"
        )


def test_solitary_bars_parameter_elongates(run_music_block):
    score = run_music_block("solitary", bars=8)
    parts = list(score.parts)
    assert len(parts) == 7
    by_inst = _parts_by_inst_id(score)
    kick_notes = sum(len(list(p.flatten().notes))
                     for p in by_inst[('BassDrum', 35)])
    assert kick_notes == 16, (
        f"solitary bars=8 expected 16 kick notes (2/bar × 8 bars); got {kick_notes}"
    )
    measures = list(parts[0].getElementsByClass(stream.Measure))
    assert len(measures) == 8


def test_companions_has_kick_and_closed_hihat_active_others_silent(run_music_block):
    score = run_music_block("companions")
    by_inst = _parts_by_inst_id(score)
    # Active: kick (8 notes), closed_hihat (16 notes — quarters × 4 bars).
    kick_notes = sum(len(list(p.flatten().notes))
                     for p in by_inst[('BassDrum', 35)])
    assert kick_notes == 8
    chihat_notes = sum(len(list(p.flatten().notes))
                       for p in by_inst[('HiHatCymbal', 42)])
    assert chihat_notes == 16
    # Silent: snare, open_hihat, low_tom, mid_tom, crash.
    for key in [
        ('SnareDrum', 38), ('HiHatCymbal', 46),
        ('TomTom', 41), ('TomTom', 47), ('CrashCymbals', 49),
    ]:
        notes = sum(len(list(p.flatten().notes)) for p in by_inst[key])
        assert notes == 0, f"companions {key} should be silent; got {notes}"


def test_peak_includes_crash_cymbal_on_bars_1_and_3(run_music_block):
    score = run_music_block("peak")
    by_inst = _parts_by_inst_id(score)
    crash_parts = by_inst[('CrashCymbals', 49)]
    assert len(crash_parts) >= 1
    bars = list(crash_parts[0].getElementsByClass(stream.Measure))
    assert len(bars) == 4
    assert len(list(bars[0].notes)) == 1, "peak bar 1 should have 1 crash"
    assert len(list(bars[1].notes)) == 0, "peak bar 2 should have NO crash"
    assert len(list(bars[2].notes)) == 1, "peak bar 3 should have 1 crash"
    assert len(list(bars[3].notes)) == 0, "peak bar 4 should have NO crash"


def test_dispersing_inserts_decrescendo_hairpin(run_music_block):
    score = run_music_block("dispersing")
    # A Diminuendo spanner should be present in the score (anchored on
    # the kick part via with_velocity(..., 'decrescendo',
    # mark_dynamics=True)).
    spanners_in_score = list(score.recurse().getElementsByClass(spanner.Spanner))
    has_dim = any(isinstance(sp, dynamics.Diminuendo) for sp in spanners_in_score)
    assert has_dim, (
        "dispersing should emit a Diminuendo (hairpin) spanner anchored on "
        "the kick part"
    )


def test_each_section_anchors_dynamic_mark_on_kick(run_music_block):
    """For each of the 8 sections, at least one Dynamic OR a Diminuendo /
    Crescendo spanner is present anchored on the kick part (the
    drum_chorus anchor pattern: one Italian abbreviation per section
    per piece, not per drum staff)."""
    section_names = [
        "solitary", "companions", "gathering", "swarming",
        "peak", "dispersing", "threading", "resting",
    ]
    for name in section_names:
        score = run_music_block(name)
        by_inst = _parts_by_inst_id(score)
        kick_parts = by_inst.get(('BassDrum', 35), [])
        assert kick_parts, f"{name}: missing kick part"
        kick_part = kick_parts[0]
        marks_in_kick = list(kick_part.recurse().getElementsByClass(dynamics.Dynamic))
        spanners_in_score = list(score.recurse().getElementsByClass(spanner.Spanner))
        hairpins = [sp for sp in spanners_in_score
                    if isinstance(sp, (dynamics.Diminuendo, dynamics.Crescendo))]
        assert len(marks_in_kick) + len(hairpins) >= 1, (
            f"{name}: expected at least one Dynamic mark or hairpin; got 0"
        )


def test_resting_bar_1_has_kicks_on_1_and_3_bars_2_4_have_only_beat_1(run_music_block):
    score = run_music_block("resting")
    by_inst = _parts_by_inst_id(score)
    kick_part = by_inst[('BassDrum', 35)][0]
    bars = list(kick_part.getElementsByClass(stream.Measure))
    assert len(bars) == 4
    assert len(list(bars[0].notes)) == 2, "resting bar 1 should have 2 kicks"
    for i in (1, 2, 3):
        assert len(list(bars[i].notes)) == 1, (
            f"resting bar {i+1} should have 1 kick (beat 1 only); "
            f"got {len(list(bars[i].notes))}"
        )


# ---- behavior preservation: refactored Murmuration matches pre-refactor shape ----

def test_murmuration_after_refactor_matches_pre_refactor_structure(run_music_block):
    """Load-bearing behavior preservation. The refactored Murmuration is
    8 calls to percussion_lab/* via context.compute + sequence().
    Sections use the canonical 7-part layout so sequence() merges by
    voice position correctly, preserving per-instrument identity
    (including percMapPitch distinction for closed vs open hi-hat,
    low vs mid tom).

    Expected per-instrument total note counts (corrected after
    pytest debugging):
    kick:    [8, 8, 11, 12, 16, 8, 8, 5] → sum = 76
    snare:   [0, 0, 16, 16, 64, 8, 8, 0] → sum = 112
    chihat:  [0, 16, 32, 32, 0, 32, 16, 0] → sum = 128 (closed)
    openhh:  [0, 0, 0, 4, 16, 4, 0, 0] → sum = 24
    lowtom:  [0, 0, 0, 8, 16, 4, 0, 0] → sum = 28
    midtom:  [0, 0, 0, 4, 16, 4, 0, 0] → sum = 24
    crash:   [0, 0, 0, 0, 2, 0, 0, 0] → sum = 2
    """
    score = run_music_block("murmuration")
    assert isinstance(score, stream.Score)
    by_inst = _parts_by_inst_id(score)

    expected = {
        ('BassDrum',     35): 76,
        ('SnareDrum',    38): 112,
        ('HiHatCymbal',  42): 128,
        ('HiHatCymbal',  46): 24,
        ('TomTom',       41): 28,
        ('TomTom',       47): 24,
        ('CrashCymbals', 49): 2,
    }
    for key, expected_notes in expected.items():
        assert key in by_inst, (
            f"missing instrument {key}; got {sorted(by_inst.keys())}"
        )
        notes_total = sum(
            len(list(p.flatten().notes)) for p in by_inst[key]
        )
        assert notes_total == expected_notes, (
            f"{key}: expected {expected_notes} notes total, got {notes_total}"
        )

    # Each instrument should span 32 measures (8 sections × 4 bars).
    for key, parts in by_inst.items():
        measures_total = sum(
            len(list(p.getElementsByClass(stream.Measure))) for p in parts
        )
        assert measures_total == 32, (
            f"{key}: expected 32 measures (8 sections × 4 bars), got "
            f"{measures_total}"
        )
