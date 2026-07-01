"""Sanity tests for the `form` library function shipped in
forge.music.lib (promoted from a vault note in forge-music v0.7.0).

`form` is the harmonic skeleton of a 12-bar blues in E: a Score with
chord symbols, no melodic content. It resolves the standard
progression to concrete chords via music21.roman.

Post-v0.7.0 migration (drain 2026-07-02-1930): these tests import
`forge.music.lib.form` directly instead of resolving via a vault +
GraphResolver. Pre-migration they silently skipped because the
vault fixture probed a promoted-and-deleted path (`blues/form.md`).

The progression data note (`twelve_bar_blues_progression`) is still
a vault-only note. Its assertion moves into a separate music21-free
check on `forge.music.lib.DEFAULT_BLUES_PROGRESSION`, which is now
the source of truth for the standard 12-bar shape (form() uses it
as its default).
"""
from music21 import stream, chord, harmony

from forge.music.lib import form, DEFAULT_BLUES_PROGRESSION


def test_form_returns_score():
    """End-to-end happy path: form runs, returns a Score with 12
    measures (one per bar of the progression). The progression is
    I I I I IV IV I I V IV I V, so 12 chord events total."""
    result = form()
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
        non_symbol = [c for c in chords if not isinstance(c, harmony.ChordSymbol)]
        symbols = list(m.getElementsByClass(harmony.ChordSymbol))
        assert non_symbol, f"measure {i+1} has no Chord (non-symbol)"
        assert symbols, f"measure {i+1} has no ChordSymbol"


def test_form_serializes_to_musicxml():
    """serialize_for_wire on the returned Score yields the wire shape
    the plugin's Verovio renderer expects: ('musicxml', <xml string>).

    Post-v0.7.0: form is a lib function, so we don't have a Snippet
    dict to pass to serialize_for_wire. Feed a minimal stub with the
    fields serialize_for_wire actually reads.
    """
    from forge.core.serialization import serialize_for_wire

    result = form()
    stub_snippet = {"meta": {"type": "action"}, "snippet_id": "form"}

    content_type, body = serialize_for_wire(result, stub_snippet)
    assert content_type == "musicxml", (
        f"expected musicxml content_type, got {content_type!r}"
    )
    assert isinstance(body, str) and body, "musicxml body is empty"
    assert body.startswith("<?xml"), (
        f"missing XML declaration; body starts: {body[:60]!r}"
    )
    assert "<score-partwise" in body, (
        f"missing <score-partwise> root tag; body starts: {body[:200]!r}"
    )


def test_default_blues_progression_is_canonical():
    """The default progression baked into lib.form matches the
    well-known 12-bar blues sequence. Pins the shape so it can't
    drift silently across lib edits."""
    assert DEFAULT_BLUES_PROGRESSION == [
        "I", "I", "I", "I",
        "IV", "IV", "I", "I",
        "V", "IV", "I", "V",
    ]
