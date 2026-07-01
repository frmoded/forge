"""Tests for the phase-shifter composition primitives.

Post-v0.7.0: phase_cell + phase_shifter are library functions in
forge.music.lib (promoted from vault notes). loom.md remains a
vault composition note that stitches them together via a Recipe.

These tests exercise the lib functions directly; the loom
composition-level test synthesizes loom's exact params (from
percussion/loom.md's Recipe) rather than resolving through the vault
+ registry, so it doesn't depend on the vault fixture.

Migrated in drain 2026-07-02-1930. Pre-migration these tests
silently skipped because the vault fixture probed a
promoted-and-deleted path.
"""
import pytest
from music21 import stream

from forge.music.lib import phase_cell, phase_shifter, closed_hihat


# Test 1
def test_phase_cell_returns_clapping_music_shape():
    """The data note-turned-lib-function returns a dict with exactly
    the Reich cell."""
    cell = phase_cell()
    assert isinstance(cell, dict)
    assert set(cell.keys()) == {"instrument", "hits_in_eighths", "length_eighths"}
    assert cell["hits_in_eighths"] == [0, 1, 2, 4, 5, 7, 9, 10]
    assert cell["length_eighths"] == 12
    assert callable(cell["instrument"]), (
        "instrument should be a factory (callable), not an instance"
    )


def _make_cell():
    return {
        "instrument": closed_hihat,
        "hits_in_eighths": [0, 1, 2, 4, 5, 7, 9, 10],
        "length_eighths": 12,
    }


# Test 2
@pytest.mark.parametrize("voices", [2, 4, 6])
def test_phase_shifter_returns_score_with_n_voices(voices):
    score = phase_shifter(
        cell=_make_cell(), num_voices=voices, bars_per_section=2, total_sections=2,
    )
    parts = list(score.parts)
    assert len(parts) == voices, f"expected {voices} parts, got {len(parts)}"


# Test 3
def test_phase_shifter_voice_1_is_anchor_never_shifts():
    """Voice 1 (K=1) has offset 0 always; first-measure hit positions
    equal the cell's hits_in_eighths in every section."""
    score = phase_shifter(
        cell=_make_cell(), num_voices=4, bars_per_section=4, total_sections=8,
    )
    voice_1 = list(score.parts)[0]
    measures = list(voice_1.getElementsByClass(stream.Measure))
    expected = _make_cell()["hits_in_eighths"]
    for bar_idx in [0, 4, 28]:
        m = measures[bar_idx]
        positions = sorted(round(n.offset / 0.5) for n in m.notes)
        assert positions == expected, (
            f"voice 1 bar {bar_idx + 1} positions {positions} != cell {expected}"
        )


# Test 4
def test_phase_shifter_voice_k_shifts_per_formula():
    """For voice K at section S: offset = (K-1) * shift * S mod cell_length.
    Pick K=3 (part index 2), S=2, shift=1 → offset = 2*1*2 = 4 eighths."""
    score = phase_shifter(
        cell=_make_cell(), num_voices=4, bars_per_section=4, total_sections=8,
        shift_per_section_eighths=1,
    )
    voice_3 = list(score.parts)[2]  # K=3 → index 2
    measures = list(voice_3.getElementsByClass(stream.Measure))
    m = measures[8]  # Section S=2 → bar index 8
    positions = sorted(round(n.offset / 0.5) for n in m.notes)
    expected_offset = (3 - 1) * 1 * 2  # = 4
    expected_positions = sorted(
        (h + expected_offset) % 12 for h in _make_cell()["hits_in_eighths"]
    )
    assert positions == expected_positions, (
        f"voice 3 section 2 positions {positions} != expected {expected_positions}"
    )


# Test 5
def test_phase_shifter_total_bar_count():
    score = phase_shifter(
        cell=_make_cell(), num_voices=4, bars_per_section=4, total_sections=8,
    )
    for i, part in enumerate(score.parts):
        measures = list(part.getElementsByClass(stream.Measure))
        assert len(measures) == 32, (
            f"part {i} has {len(measures)} measures, expected 32"
        )


# Test 6
def test_loom_composition_pins_reich_realignment():
    """loom.md's Recipe: phase_shifter(cell=phase_cell(), num_voices=4,
    bars_per_section=4, total_sections=8, shift_per_section_eighths=1,
    ts_str="12/8", bpm=96, velocity_profile="human").

    Synthesize the same composition here and assert the Reich-realignment
    invariant: voice 4 (K=4) realigns with voice 1 at section S=4 → bar
    index 16 (0-indexed measure). Voice 4 bar 17 hit positions should
    equal voice 1 bar 1 hit positions.
    """
    cell = phase_cell()
    score = phase_shifter(
        cell=cell, num_voices=4, bars_per_section=4, total_sections=8,
        shift_per_section_eighths=1, ts_str="12/8", bpm=96,
        velocity_profile="human",
    )
    assert isinstance(score, stream.Score)
    parts = list(score.parts)
    assert len(parts) == 4
    for i, p in enumerate(parts):
        measures = list(p.getElementsByClass(stream.Measure))
        assert len(measures) == 32, (
            f"loom part {i} has {len(measures)} bars, expected 32"
        )
    voice_1_bar_1 = sorted(
        round(n.offset / 0.5)
        for n in list(parts[0].getElementsByClass(stream.Measure))[0].notes
    )
    voice_4_bar_17 = sorted(
        round(n.offset / 0.5)
        for n in list(parts[3].getElementsByClass(stream.Measure))[16].notes
    )
    assert voice_4_bar_17 == voice_1_bar_1, (
        f"voice 4 should realign with voice 1 at bar 17; "
        f"v1={voice_1_bar_1}, v4@17={voice_4_bar_17}"
    )
