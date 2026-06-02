"""Tests for the three-snippet Loom composition (v0.3.7).

phase_cell + phase_shifter + loom demonstrate Forge's snippet-composition
primitives — data snippet returning a dict, function-style snippet
taking args via context.compute(snippet_id, *args, **kwargs), and a
composition snippet wiring them together.

Tests run via the existing `run_music_block` fixture which scans the
user's forge-music vault. The phase_shifter cases construct an
in-memory cell and invoke phase_shifter as a Python function (we can
do this because we have a resolved Snippet body); the integration
test goes through context.compute end-to-end.
"""
import pytest
from music21 import stream


# Test 1
def test_phase_cell_returns_clapping_music_shape(run_music_block):
    """The data snippet returns a dict with exactly the Reich cell."""
    cell = run_music_block("phase_cell")
    assert isinstance(cell, dict)
    assert set(cell.keys()) == {"instrument", "hits_in_eighths", "length_eighths"}
    assert cell["hits_in_eighths"] == [0, 1, 2, 4, 5, 7, 9, 10]
    assert cell["length_eighths"] == 12
    assert callable(cell["instrument"]), (
        "instrument should be a factory (callable), not an instance"
    )


def _resolve_phase_shifter_compute(music_resolver):
    """Resolve phase_shifter and return its compute() function ready to
    call. The fixture pattern in conftest builds inputs/resolver each call;
    we replicate that here so each test can call compute(cell, **kwargs)
    directly without going through context.compute."""
    res, reg, vault = music_resolver
    from forge.core.executor import extract_python, ForgeContext
    snip = res.resolve("phase_shifter")
    code = extract_python(snip["body"])
    ns = {}
    # The Python facet uses globals that the executor would normally pre-inject
    # via the music domain (meter, tempo, stream, note, instrument, with_velocity,
    # closed_hihat, etc.). Build the same namespace.
    from forge.core.executor import _domain_globals_for
    import builtins, random, math, numpy
    ns.update(_domain_globals_for(["music"]))
    ns["random"] = random
    ns["math"] = math
    ns["numpy"] = numpy
    ns["__builtins__"] = builtins.__dict__
    exec(compile(code, "<phase_shifter>", "exec"), ns)
    fn = ns["compute"]
    # Build a ForgeContext that the function can be called with; it never
    # calls context.compute() so a thin one is fine.
    ctx = ForgeContext(res, {}, vault_path=vault, registry=reg,
                       caller_id="forge-music/percussion/phase_shifter")
    return fn, ctx


def _make_cell():
    from forge.music.lib import closed_hihat
    return {
        "instrument": closed_hihat,
        "hits_in_eighths": [0, 1, 2, 4, 5, 7, 9, 10],
        "length_eighths": 12,
    }


# Test 2
@pytest.mark.parametrize("voices", [2, 4, 6])
def test_phase_shifter_returns_score_with_n_voices(music_resolver, voices):
    fn, ctx = _resolve_phase_shifter_compute(music_resolver)
    cell = _make_cell()
    score = fn(ctx, cell, voices=voices, bars_per_section=2, total_sections=2)
    parts = list(score.parts)
    assert len(parts) == voices, f"expected {voices} parts, got {len(parts)}"


# Test 3
def test_phase_shifter_voice_1_is_anchor_never_shifts(music_resolver):
    """Voice 1 (K=1) has offset 0 always; first-measure hit positions
    equal the cell's hits_in_eighths in every section."""
    fn, ctx = _resolve_phase_shifter_compute(music_resolver)
    cell = _make_cell()
    score = fn(ctx, cell, voices=4, bars_per_section=4, total_sections=8)
    voice_1 = list(score.parts)[0]
    measures = list(voice_1.getElementsByClass(stream.Measure))
    expected = cell["hits_in_eighths"]
    # Sample bar 1 (section 0, bar 0) and bar 5 (section 1, bar 0) and
    # bar 29 (section 7, bar 0) — all should be the unshifted cell.
    for bar_idx in [0, 4, 28]:
        m = measures[bar_idx]
        positions = sorted(round(n.offset / 0.5) for n in m.notes)
        assert positions == expected, (
            f"voice 1 bar {bar_idx + 1} positions {positions} != cell {expected}"
        )


# Test 4
def test_phase_shifter_voice_k_shifts_per_formula(music_resolver):
    """For voice K at section S: offset = (K-1) * shift * S mod cell_length.
    Pick K=3 (part index 2), S=2, shift=1 → offset = 2*1*2 = 4 eighths."""
    fn, ctx = _resolve_phase_shifter_compute(music_resolver)
    cell = _make_cell()
    score = fn(ctx, cell, voices=4, bars_per_section=4, total_sections=8,
               shift_per_section_eighths=1)
    voice_3 = list(score.parts)[2]  # K=3 → index 2
    measures = list(voice_3.getElementsByClass(stream.Measure))
    # Section S=2 → bar index 8 (section 2's first bar = sections 0 and 1 of 4 bars each).
    m = measures[8]
    positions = sorted(round(n.offset / 0.5) for n in m.notes)
    expected_offset = (3 - 1) * 1 * 2  # = 4
    expected_positions = sorted((h + expected_offset) % 12 for h in cell["hits_in_eighths"])
    assert positions == expected_positions, (
        f"voice 3 section 2 positions {positions} != expected {expected_positions}"
    )


# Test 5
def test_phase_shifter_total_bar_count(music_resolver):
    fn, ctx = _resolve_phase_shifter_compute(music_resolver)
    cell = _make_cell()
    score = fn(ctx, cell, voices=4, bars_per_section=4, total_sections=8)
    for i, part in enumerate(score.parts):
        measures = list(part.getElementsByClass(stream.Measure))
        assert len(measures) == 32, (
            f"part {i} has {len(measures)} measures, expected 32"
        )


# Test 6
def test_loom_composes_via_context_compute(run_music_block):
    """End-to-end integration: loom calls context.compute('phase_cell')
    and context.compute('phase_shifter', cell, **kwargs). The returned
    Score has 4 parts × 32 measures."""
    score = run_music_block("loom")
    assert isinstance(score, stream.Score)
    parts = list(score.parts)
    assert len(parts) == 4
    for i, p in enumerate(parts):
        measures = list(p.getElementsByClass(stream.Measure))
        assert len(measures) == 32, (
            f"loom part {i} has {len(measures)} bars, expected 32"
        )
    # Sanity: voice 4 (K=4) realigns with voice 1 at section S=4 → bar 17
    # (0-indexed measure index 16). Voice 4 bar 17 hit positions should
    # equal voice 1 bar 1 hit positions.
    voice_1_bar_1 = sorted(
        round(n.offset / 0.5) for n in list(parts[0].getElementsByClass(stream.Measure))[0].notes
    )
    voice_4_bar_17 = sorted(
        round(n.offset / 0.5) for n in list(parts[3].getElementsByClass(stream.Measure))[16].notes
    )
    assert voice_4_bar_17 == voice_1_bar_1, (
        f"voice 4 should realign with voice 1 at bar 17; "
        f"v1={voice_1_bar_1}, v4@17={voice_4_bar_17}"
    )
