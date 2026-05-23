"""Sanity tests for the blues `form` snippet shipped in forge-music v0.3.0.

`form` is the harmonic skeleton of a 12-bar blues in E: a Score with
chord symbols, no melodic content. It calls a sibling data snippet
(`twelve_bar_blues_progression`) for the I/IV/V roman-numeral
progression and resolves to concrete chords in E major via
`music21.roman`.

These run through the engine's resolver + executor (same path the
generic `/compute` endpoint uses internally), then assert on the
returned `music21.stream.Score` and on the engine's wire serialization
of it (`serialize_for_wire` → MusicXML). The Score itself is
inspectable for chord counts and chord-symbol presence; the MusicXML
serialization is the wire shape the Obsidian plugin's Verovio
renderer eventually receives.
"""
from music21 import stream, chord, harmony


def test_form_returns_score(run_music_block):
    """End-to-end happy path: form runs, returns a Score with 12
    measures (one per bar of the progression). The progression is
    I I I I IV IV I I V IV I V, so 12 chord events total."""
    result = run_music_block("form")
    assert isinstance(result, stream.Score), (
        f"expected stream.Score, got {type(result).__name__}"
    )

    # One Part inside the Score (form builds a single Part for the
    # piano voicing of the progression).
    parts = list(result.parts)
    assert len(parts) == 1, f"expected 1 part, got {len(parts)}"

    # Twelve measures.
    measures = list(parts[0].getElementsByClass(stream.Measure))
    assert len(measures) == 12, (
        f"expected 12 measures (one per bar), got {len(measures)}"
    )

    # Each measure has a Chord (the harmonic event) and a ChordSymbol
    # (the label for the chord). Check both are present.
    for i, m in enumerate(measures):
        chords = list(m.getElementsByClass(chord.Chord))
        # ChordSymbol is a subclass of Chord in music21; filter the raw
        # list to actual non-symbol Chord objects.
        non_symbol = [c for c in chords if not isinstance(c, harmony.ChordSymbol)]
        symbols = list(m.getElementsByClass(harmony.ChordSymbol))
        assert non_symbol, f"measure {i+1} has no Chord (non-symbol)"
        assert symbols, f"measure {i+1} has no ChordSymbol"


def test_form_serializes_to_musicxml(run_music_block, music_resolver):
    """serialize_for_wire on the returned Score yields the wire shape
    the plugin's Verovio renderer expects: ('musicxml', <xml string>).
    The string must be well-formed MusicXML — root element
    <score-partwise> per MusicXML 3.x partwise convention (music21's
    default exporter)."""
    from forge.core.serialization import serialize_for_wire

    res, _reg, _vault = music_resolver
    form_snippet = res.resolve("form")
    result = run_music_block("form")

    content_type, body = serialize_for_wire(result, form_snippet)
    assert content_type == "musicxml", (
        f"expected musicxml content_type, got {content_type!r}"
    )
    assert isinstance(body, str) and body, "musicxml body is empty"
    # Well-formedness: XML declaration + score-partwise root.
    assert body.startswith("<?xml"), (
        f"missing XML declaration; body starts: {body[:60]!r}"
    )
    assert "<score-partwise" in body, (
        f"missing <score-partwise> root tag; body starts: {body[:200]!r}"
    )


def test_twelve_bar_blues_progression_returns_data(music_resolver):
    """The data snippet returns the canonical 12-bar roman-numeral list.
    Asserts shape (12 strings) and the well-known sequence so the
    progression doesn't drift silently across vault edits. Reads via
    `read_data_snippet` rather than `run_music_block` because the
    block-runner fixture is action-only (data snippets don't have a
    Python facet to exec)."""
    from forge.core.executor import read_data_snippet

    res, _reg, _vault = music_resolver
    snip = res.resolve("twelve_bar_blues_progression")
    progression = read_data_snippet(snip)
    assert progression == [
        "I", "I", "I", "I",
        "IV", "IV", "I", "I",
        "V", "IV", "I", "V",
    ]
