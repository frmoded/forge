"""Bar-arithmetic invariant tests for blues snippets.

v0.2.27 made the music domain work end-to-end in Pyodide. First
production smoke against blues content surfaced an overflow bug:
`vocal_phrase_a.md` produces measures totaling 7.0 quarterLength in
12/8 (expected 6.0). Root cause: the trailing
`note.Rest(quarterLength=bar_ql - total)` is silently created as
`Rest(quarterLength=1.0)` when `bar_ql - total == 0` — music21's Rest
defaults to quarterLength=1 when 0 is passed, not 0. Every measure in
the snippet already summed to exactly bar_ql before the trailing rest,
so the unconditional trailing-rest append added 1.0 to each bar.

This bug propagates into chorus (which calls vocal_phrase_a) and song
(which calls chorus): the investigation script found 4 overflowing
measures in vocal_phrase_a, 8 in chorus, 24 in song. Fix the leaf
snippet and the chain becomes clean.

These tests run blues snippet bodies through the engine's
exec_python and assert every Measure in the resulting Score sums to
the time signature's `barDuration.quarterLength`. Tests skip on
clones without the sibling `~/projects/forge-music/` vault (per the
existing `music_resolver` fixture).
"""
from music21 import stream


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


def test_vocal_phrase_a_bars_sum_to_bar_ql(run_music_block):
    """The load-bearing leaf snippet — the bug originates here.
    vocal_phrase_a builds 4 measures manually; every Measure's
    notes+rests must total ts.barDuration.quarterLength (6.0 for
    12/8). Pre-fix: all 4 measures sum to 7.0 (unconditional
    trailing-rest append where remaining time is already 0)."""
    result = run_music_block("vocal_phrase_a")
    bad = _measure_totals(result)
    assert bad == [], (
        f"vocal_phrase_a has measures that don't sum to 6.0 (bar_ql for "
        f"12/8): {bad}. Each tuple is (part_idx, measure_number, total). "
        "Pre-fix expectation: 4 measures at 7.0 from Rest(0) → Rest(1.0)."
    )


def test_chorus_bars_sum_to_bar_ql(run_music_block):
    """Downstream of vocal_phrase_a — the bug should propagate through
    chorus. Post-fix to vocal_phrase_a, chorus measures should also
    sum cleanly. This is a regression-shape test that locks in the
    leaf fix flowing through the composition."""
    result = run_music_block("chorus")
    bad = _measure_totals(result)
    assert bad == [], (
        f"chorus has measures that don't sum to 6.0: {bad}. "
        "Pre-fix expectation: 8 measures in the vocal part (the "
        "two vocal_phrase_a contributions across the AAB) at 7.0."
    )


def test_song_bars_sum_to_bar_ql(run_music_block):
    """Top-of-chain regression test. song = chorus × 3 + solo_chorus.
    With the leaf fix, the full song should have zero overflowing
    measures across all 48 bars."""
    result = run_music_block("song")
    bad = _measure_totals(result)
    assert bad == [], (
        f"song has measures that don't sum to 6.0: {bad}. "
        "Pre-fix expectation: 24 measures across choruses 1, 2, 3 "
        "(8 each) in the vocal part at 7.0."
    )


def test_drums_shuffle_returns_valid_score(run_music_block):
    """v0.3.5 spike: drums_shuffle computes to a Score with at least
    one Part. Every Measure's notes+rests sum to 6.0 quarterLength
    per the 12/8 invariant. Detailed rendering quality is a user-side
    eyeball, not a suite assertion — this test just locks in the
    structural contract."""
    result = run_music_block("drums_shuffle")
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


def test_vocal_phrase_b_bars_already_clean(run_music_block):
    """Investigation found vocal_phrase_b's measures already sum to
    6.0 — its trailing-rest pattern doesn't hit the Rest(0)→Rest(1.0)
    trap because its internal totals leave nonzero remaining time.
    Lock this in: a future content edit shouldn't accidentally
    introduce the same trap here."""
    result = run_music_block("vocal_phrase_b")
    bad = _measure_totals(result)
    assert bad == [], (
        f"vocal_phrase_b was clean pre-fix; should stay clean: {bad}"
    )


def test_vocal_phrase_a_shape_preserved_through_bar_migration(run_music_block):
    """Phase B (v0.3.3) migrated vocal_phrase_a from manual stream.Measure
    + _pad to lib.bar(). The output shape must be unchanged: 1 Part
    containing 4 Measures, each summing to bar_ql=6.0 (which the
    bar-arithmetic test above covers). This test locks in the structural
    shape so a future refactor can't silently drop a measure or split
    the Part."""
    result = run_music_block("vocal_phrase_a")
    assert isinstance(result, stream.Score), (
        f"expected Score, got {type(result).__name__}"
    )
    parts = list(result.parts)
    assert len(parts) == 1, f"expected 1 Part, got {len(parts)}"
    measures = list(parts[0].getElementsByClass(stream.Measure))
    assert len(measures) == 4, (
        f"expected 4 Measures (the four phrase bars), got {len(measures)}"
    )


def test_minor_pentatonic_intent_documented_in_vocal_phrase_a(music_vault):
    """Mode-forcing audit: vocal_phrase_a calls pentatonic(..., mode='minor', ...)
    regardless of form's declared mode (form uses major). This is
    intentional blues convention (minor pentatonic vocal line over
    major-mode chord progression), but undocumented it looks like a
    bug. The English facet must explicitly explain the override so a
    future content edit doesn't 'fix' it accidentally."""
    import os
    path = os.path.join(music_vault, "blues", "vocal_phrase_a.md")
    with open(path) as f:
        content = f.read()
    # English facet is the section between '# English' and '---' or '# Python'.
    english_end = content.find("# Python")
    english_section = content[:english_end] if english_end != -1 else content
    # The note doesn't have to be verbatim; just verify the intent is
    # explained in some readable form.
    keywords = ["minor pentatonic", "minor-pentatonic"]
    has_minor_pentatonic_note = any(k in english_section for k in keywords)
    assert has_minor_pentatonic_note, (
        "vocal_phrase_a English facet should mention 'minor pentatonic' "
        "(or 'minor-pentatonic') so the deliberate override of form's "
        "major mode is visible to future content authors. Current English: "
        f"\n{english_section[:500]}..."
    )


def test_minor_pentatonic_intent_documented_in_vocal_phrase_b(music_vault):
    """Same convention as vocal_phrase_a — vocal_phrase_b also forces
    minor pentatonic. English must say so."""
    import os
    path = os.path.join(music_vault, "blues", "vocal_phrase_b.md")
    with open(path) as f:
        content = f.read()
    english_end = content.find("# Python")
    english_section = content[:english_end] if english_end != -1 else content
    keywords = ["minor pentatonic", "minor-pentatonic"]
    has_minor_pentatonic_note = any(k in english_section for k in keywords)
    assert has_minor_pentatonic_note, (
        "vocal_phrase_b English facet should mention 'minor pentatonic' "
        "to document the deliberate mode override."
    )


def test_minor_pentatonic_intent_documented_in_guitar_solo_chorus(music_vault):
    """guitar_solo_chorus also forces minor pentatonic — convention
    for blues instrumental solo. English must say so."""
    import os
    path = os.path.join(music_vault, "blues", "guitar_solo_chorus.md")
    with open(path) as f:
        content = f.read()
    english_end = content.find("# Python")
    english_section = content[:english_end] if english_end != -1 else content
    keywords = ["minor pentatonic", "minor-pentatonic"]
    has_minor_pentatonic_note = any(k in english_section for k in keywords)
    assert has_minor_pentatonic_note, (
        "guitar_solo_chorus English facet should mention 'minor pentatonic'."
    )
