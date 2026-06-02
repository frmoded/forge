"""Tests for percussion-partition content (v0.3.6).

murmuration is the first piece in `~/projects/forge-music/percussion/`.
32 bars in 4/4, 7 instrumental Parts (kick, snare, closed hi-hat, open
hi-hat, low tom, mid tom, crash cymbal). Velocity arc carries the
section-by-section dynamic story; structural shape is fixed (32 bars
per part, every bar sums to 4.0 quarterLength).

These tests run via the existing `run_music_block` fixture from
`tests/music/conftest.py` which scans the user's forge-music vault.
"""
from music21 import stream


def test_murmuration_returns_valid_score(run_music_block):
    """Structural contract: Score with >= 5 Parts; every Part has 32
    measures; every measure totals 4.0 quarterLength (the 4/4
    invariant). The exact Part count depends on the realization but
    must be >= 5 (kick, snare, hi-hat, tom, crash at minimum)."""
    result = run_music_block("murmuration")
    assert isinstance(result, stream.Score), (
        f"expected Score, got {type(result).__name__}"
    )
    parts = list(result.parts)
    assert len(parts) >= 5, (
        f"expected >= 5 Parts (kick, snare, hi-hat, tom, crash min), "
        f"got {len(parts)}"
    )
    for part in parts:
        measures = list(part.getElementsByClass(stream.Measure))
        assert len(measures) == 32, (
            f"part {part.id} has {len(measures)} bars, expected 32"
        )
        for m in measures:
            total = sum(el.duration.quarterLength for el in m.notesAndRests)
            assert abs(total - 4.0) < 1e-6, (
                f"part {part.id} measure {m.number} total = {total}, "
                f"expected 4.0"
            )


def test_murmuration_has_velocity_variation(run_music_block):
    """The piece should exhibit velocity variation — robotic uniform
    velocity (every hit at 90) would defeat the with_velocity()
    helper's purpose. Asserts at least 5 distinct velocity values
    across all notes; the realization should produce many more (the
    'human' / 'crescendo' / 'decrescendo' profiles each generate a
    spread)."""
    result = run_music_block("murmuration")
    velocities = []
    for part in result.parts:
        for n in part.flatten().notes:
            if hasattr(n, 'volume') and n.volume.velocity is not None:
                velocities.append(n.volume.velocity)
    distinct = set(velocities)
    assert len(distinct) >= 5, (
        f"only {len(distinct)} distinct velocity values across the piece "
        f"({sorted(distinct)}) — velocity variation isn't landing as designed"
    )
