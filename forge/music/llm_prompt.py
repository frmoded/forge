"""Music-domain prompt fragment for /generate.

This file is intended to be edited freely by music-focused iterations; the
core LLM machinery doesn't import any text from here. Importing this module
registers the fragment with forge.core.llm_prompts.

Stylistic note for future editors: the fragment is a single multi-line
string. Keep it self-contained — assume the reader has already seen the base
prompt's snippet conventions, but don't rely on knowing what other fragments
are present.
"""

from forge.core.llm_prompts import register_fragment


MUSIC_PROMPT_FRAGMENT = """Music21 modules already bound as globals (do NOT write `from music21 import ...`
or `import music21`):
  music21, stream, note, chord, meter, key, tempo, pitch, duration, instrument, harmony.

For music output: return a music21.stream.Stream (Score / Part / Measure / ...).
The runtime serializes it to MusicXML and the plugin renders it as engraved
notation. Do NOT return dicts of pitch/beat data — return real notes.

Music21 idioms — common pitfalls to avoid:

- MetronomeMark referent must match the beat unit, not the smallest note.
  For 4/4 use referent=duration.Duration('quarter'). For compound meters
  (12/8, 6/8, 9/8) use a dotted quarter:
  duration.Duration(type='quarter', dots=1).

- Every stream.Part should have an instrument set as its first element
  (e.g. part.append(instrument.AcousticGuitar())). Without one, music21
  silently defaults to Piano in both engraving labels and MIDI playback.

- For chord-symbol notation (lead-sheet style), use harmony.ChordSymbol
  ONLY. Do not also call chord.addLyric() with the same label — that
  duplicates the chord name above and below the staff. addLyric is for
  sung text, not chord names.

- When placing a chord symbol and a chord at the start of a Measure,
  prefer m.insert(0, cs) and m.insert(0, c) over append() so the offset
  is explicit.

- Don't hardcode bar length in quarterLength. Derive it from the time
  signature: meter.TimeSignature('12/8').barDuration.quarterLength."""


register_fragment(MUSIC_PROMPT_FRAGMENT)
