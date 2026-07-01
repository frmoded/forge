"""Bar-arithmetic invariant tests for blues snippets.

v0.2.27 made the music domain work end-to-end in Pyodide. First
production smoke against blues content surfaced an overflow bug in
vocal_phrase_a's measure padding: the trailing rest was inserted
even when remaining time was already 0, causing every bar to sum to
7.0 quarterLength in 12/8 (expected 6.0). Fix propagated through the
chain (chorus + song).

Post-v0.7.0 (drain 2026-07-02-1930): vocal_phrase_a, vocal_phrase_b,
drums_shuffle, guitar_solo_chorus are library functions in
forge.music.lib. Tests call them directly. chorus + slow_burn (was
song) remain vault-level composition notes; tests use
run_music_block to exercise the composition path end-to-end.

Post-v0.8.0: song.md was renamed to slow_burn/slow_burn.md; the
song-level regression test now resolves `slow_burn`.
"""
from music21 import stream

from forge.music.lib import (
    vocal_phrase_a,
    vocal_phrase_b,
    drums_shuffle,
)


def _measure_totals(score, expected_bar_ql=6.0):
    """Walk every Measure in every Part; return list of
    (part_idx, measure_number, total) for any measure whose
    notes+rests don't sum to expected_bar_ql."""
    bad = []
    for part_idx, part in enumerate(score.parts):
        for m in part.getElementsByClass(stream.Measure):
            total = sum(
                getattr(el, "quarterLength", 0)
                for el in m.notesAndRests
            )
            if abs(total - expected_bar_ql) > 1e-9:
                bad.append((part_idx, m.number, round(total, 4)))
    return bad


def test_vocal_phrase_a_bars_sum_to_bar_ql():
    """The load-bearing leaf — the bug originated here.
    vocal_phrase_a builds 4 measures; every Measure's notes+rests
    must total ts.barDuration.quarterLength (6.0 for 12/8)."""
    result = vocal_phrase_a()
    bad = _measure_totals(result)
    assert bad == [], (
        f"vocal_phrase_a has measures that don't sum to 6.0: {bad}. "
        "Pre-fix expectation: 4 measures at 7.0 from Rest(0) → Rest(1.0)."
    )


def test_chorus_bars_sum_to_bar_ql(run_music_block):
    """Downstream of vocal_phrase_a — the bug should propagate through
    chorus. Post-fix to vocal_phrase_a, chorus measures should also
    sum cleanly. Vault-level composition; exercises the caller-scoped
    resolution path end-to-end."""
    result = run_music_block("chorus")
    bad = _measure_totals(result)
    assert bad == [], (
        f"chorus has measures that don't sum to 6.0: {bad}. "
        "Pre-fix expectation: 8 measures in the vocal part at 7.0."
    )


def test_slow_burn_bars_sum_to_bar_ql(run_music_block):
    """Top-of-chain regression. slow_burn (was song.md pre-v0.8.0) =
    chorus × 3 + solo_chorus. With the leaf fix, the full piece should
    have zero overflowing measures across all 48 bars."""
    result = run_music_block("slow_burn")
    bad = _measure_totals(result)
    assert bad == [], (
        f"slow_burn has measures that don't sum to 6.0: {bad}. "
        "Pre-fix expectation: 24 measures across choruses 1, 2, 3 "
        "(8 each) in the vocal part at 7.0."
    )


def test_drums_shuffle_returns_valid_score():
    """v0.3.5: drums_shuffle computes to a Score with at least one Part.
    Every Measure's notes+rests sum to 6.0 quarterLength per the 12/8
    invariant."""
    result = drums_shuffle()
    assert isinstance(result, stream.Score)
    parts = list(result.parts)
    assert len(parts) >= 1, "drums_shuffle should produce at least one Part"
    for part in parts:
        for m in part.getElementsByClass(stream.Measure):
            total = sum(el.duration.quarterLength for el in m.notesAndRests)
            assert abs(total - 6.0) < 1e-6, (
                f"part {part.partName or part.id!r} measure {m.number} "
                f"total = {total}, expected 6.0"
            )


def test_vocal_phrase_b_bars_already_clean():
    """Investigation found vocal_phrase_b's measures already sum to
    6.0. Lock this in: a future edit shouldn't accidentally introduce
    the same trap."""
    result = vocal_phrase_b()
    bad = _measure_totals(result)
    assert bad == [], (
        f"vocal_phrase_b was clean pre-fix; should stay clean: {bad}"
    )


def test_vocal_phrase_a_shape_preserved_through_bar_migration():
    """Phase B (v0.3.3) migrated vocal_phrase_a from manual
    stream.Measure + _pad to lib.bar(). The output shape must be
    unchanged: 1 Part containing 4 Measures, each summing to 6.0."""
    result = vocal_phrase_a()
    assert isinstance(result, stream.Score), (
        f"expected Score, got {type(result).__name__}"
    )
    parts = list(result.parts)
    assert len(parts) == 1, f"expected 1 Part, got {len(parts)}"
    measures = list(parts[0].getElementsByClass(stream.Measure))
    assert len(measures) == 4, (
        f"expected 4 Measures (the four phrase bars), got {len(measures)}"
    )
