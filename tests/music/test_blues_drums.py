"""Content invariants for the blues song's drum integration (v0.3.x preview).

Adds a parameterized drum_chorus snippet + per-chorus profile selection
in song.md. Tests verify each profile's shape (instruments, hit count,
crash presence) and that the song now overlays drum parts on top of
the existing chorus/solo_chorus content.

Preview mode (per the 2026-06-02-2315 prompt) — these tests live in
the engine repo for normal pytest runs, but the snippet changes in
forge-music are uncommitted at drain time. If the user reverts the
preview, this test file should also be removed (or it'll fail on
missing drum_chorus snippet).
"""
from music21 import stream, instrument


def test_drum_chorus_default_profile_returns_12_bar_score(run_music_block):
    """Default profile = 'standard'. Returns a Score with multiple
    Parts, each containing 12 measures in 12/8."""
    result = run_music_block("drum_chorus")
    assert isinstance(result, stream.Score)
    parts = list(result.parts)
    assert len(parts) >= 3, (
        f"standard profile should have >=3 drum parts (kick + snare + hi-hat), "
        f"got {len(parts)}"
    )
    for p in parts:
        measures = list(p.getElementsByClass(stream.Measure))
        assert len(measures) == 12, (
            f"drum_chorus part has {len(measures)} bars, expected 12"
        )


def _total_notes(score):
    return sum(len(list(p.flatten().notes)) for p in score.parts)


def test_drum_chorus_sparse_profile_has_fewer_hits_than_driving(run_music_block):
    """Sparse: kick on 1+3, snare on 2+4 + ghost (3 hits/bar/voice-ish),
    sparse hi-hat. Driving: kick on all 4, snare on 2+4, ride on all 4,
    crash bar 1. Driving should produce notably more notes."""
    sparse = run_music_block("drum_chorus", profile='sparse')
    driving = run_music_block("drum_chorus", profile='driving')
    n_sparse = _total_notes(sparse)
    n_driving = _total_notes(driving)
    assert n_sparse < n_driving, (
        f"sparse={n_sparse} notes >= driving={n_driving}; "
        "profiles should differentiate by density"
    )


def test_drum_chorus_driving_profile_includes_crash_on_bar_1(run_music_block):
    """Driving profile has crash on bar 1, beat 1. Find the Crash part
    and assert measure 1 has at least one note."""
    score = run_music_block("drum_chorus", profile='driving')
    crash_part = None
    for p in score.parts:
        inst = next((el for el in p.elements
                     if isinstance(el, instrument.Instrument)), None)
        if isinstance(inst, instrument.CrashCymbals):
            crash_part = p
            break
    assert crash_part is not None, "driving profile should include a crash cymbal part"
    bar1 = list(crash_part.getElementsByClass(stream.Measure))[0]
    bar1_notes = list(bar1.notes)
    assert len(bar1_notes) >= 1, "crash should have at least one note in bar 1"


def test_drum_chorus_sparse_profile_omits_crash(run_music_block):
    """Sparse profile: no crash cymbal part."""
    score = run_music_block("drum_chorus", profile='sparse')
    for p in score.parts:
        inst = next((el for el in p.elements
                     if isinstance(el, instrument.Instrument)), None)
        assert not isinstance(inst, instrument.CrashCymbals), (
            "sparse profile should not include a crash cymbal part"
        )


def test_drum_chorus_standard_profile_has_hihat_on_all_4_beats(run_music_block):
    """Standard profile: closed hi-hat on all 4 dotted-quarter beats
    (positions 0.0, 1.5, 3.0, 4.5 in 12/8). Find the HiHatCymbal part;
    assert bar 1 has 4 notes at those offsets."""
    score = run_music_block("drum_chorus", profile='standard')
    hh_part = None
    for p in score.parts:
        inst = next((el for el in p.elements
                     if isinstance(el, instrument.Instrument)), None)
        if isinstance(inst, instrument.HiHatCymbal):
            hh_part = p
            break
    assert hh_part is not None, "standard profile should include a hi-hat part"
    bar1 = list(hh_part.getElementsByClass(stream.Measure))[0]
    offsets = sorted(n.offset for n in bar1.notes)
    assert offsets == [0.0, 1.5, 3.0, 4.5], (
        f"hi-hat bar 1 offsets {offsets} != [0.0, 1.5, 3.0, 4.5]"
    )


def test_drum_chorus_inserts_section_dynamic_mark(run_music_block):
    """Sparse profile uses with_velocity(60, mark_dynamics=True) which
    maps to 'mp' (band 46-72). Assert the Score contains at least one
    Dynamic with value 'mp'."""
    from music21 import dynamics
    score = run_music_block("drum_chorus", profile='sparse')
    all_marks = []
    for p in score.parts:
        for el in p.recurse():
            if isinstance(el, dynamics.Dynamic):
                all_marks.append(el.value)
    assert 'mp' in all_marks, (
        f"sparse profile should produce an 'mp' dynamic mark; "
        f"got {all_marks}"
    )


def test_song_now_includes_drum_parts_per_section(run_music_block):
    """song overlays drum_chorus on each of the 4 sections. The
    returned Score should include drum instruments (BassDrum,
    SnareDrum, plus at least one of HiHatCymbal/RideCymbals/
    CrashCymbals depending on profile). Total measure count per
    drum part = 48 bars (4 sections × 12)."""
    song = run_music_block("song")
    assert isinstance(song, stream.Score)
    parts = list(song.parts)

    drum_classes = {
        type(next((el for el in p.elements
                   if isinstance(el, instrument.Instrument)), None))
        for p in parts
    }
    # Drop None (parts with no instrument set somehow).
    drum_classes.discard(type(None))

    has_kick = instrument.BassDrum in drum_classes
    has_snare = instrument.SnareDrum in drum_classes
    has_hh_or_ride_or_crash = any(
        cls in drum_classes for cls in (
            instrument.HiHatCymbal, instrument.RideCymbals, instrument.CrashCymbals,
        )
    )
    assert has_kick, f"song should include BassDrum; saw classes: {drum_classes}"
    assert has_snare, f"song should include SnareDrum; saw classes: {drum_classes}"
    assert has_hh_or_ride_or_crash, (
        f"song should include at least one cymbal/hat; saw classes: {drum_classes}"
    )

    # Each drum part should have 48 measures (4 sections × 12).
    for p in parts:
        inst = next((el for el in p.elements
                     if isinstance(el, instrument.Instrument)), None)
        if isinstance(inst, (instrument.BassDrum, instrument.SnareDrum,
                             instrument.HiHatCymbal, instrument.RideCymbals,
                             instrument.CrashCymbals)):
            measures = list(p.getElementsByClass(stream.Measure))
            assert len(measures) == 48, (
                f"drum part with {type(inst).__name__} has {len(measures)} "
                f"bars, expected 48 (4 choruses × 12)"
            )
