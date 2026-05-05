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

- harmony.ChordSymbol is engraving-only — it labels the staff but
  produces NO MIDI sound. To make the chord audible, also insert a
  sounding chord at the same offset:
    cs = harmony.ChordSymbol("E7"); m.insert(0, cs)
    c  = chord.Chord(cs.pitches, quarterLength=bar_ql); m.insert(0, c)
  Without the chord.Chord (or notes/Rests with actual pitches), playback
  is silent for that measure regardless of the instrument set.

- When placing a chord symbol and a chord at the start of a Measure,
  prefer m.insert(0, cs) and m.insert(0, c) over append() so the offset
  is explicit.

- Don't hardcode bar length in quarterLength. Derive it from the time
  signature: meter.TimeSignature('12/8').barDuration.quarterLength.

- Every Measure's notes and rests must total exactly the time signature's
  bar length: ts.barDuration.quarterLength (6.0 for 12/8, 4.0 for 4/4,
  3.0 for 3/4). Do not write bars that fall short or overflow. When in
  doubt, fill remaining time with a Rest.

- Do not derive sub-durations from bar_ql by guessing divisors. Use
  literal music21 quarterLength values directly: eighth = 0.5,
  quarter = 1.0, dotted_quarter = 1.5, half = 2.0, whole = 4.0. These
  values do NOT depend on the time signature. Only `bar_ql` (the total
  bar length) varies with the time signature.

- Use only the modules listed above (stream, note, chord, meter, key,
  tempo, pitch, duration, instrument, harmony). Do not reach into other
  music21 submodules via `music21.<other>` (articulations, expressions,
  etc.) — they are not injected and will raise AttributeError.

- Do not write dead code. Every helper function defined must be called,
  every variable assigned must be read, every conditional must have
  meaningfully different branches. Delete unused declarations before
  returning.

- Avoid bend, glissando, and continuous-pitch articulations — Verovio
  renders them poorly. When the English asks for a bend, prefer a
  discrete approach note (a grace-note-length pitch one scale step
  below the target, placed BEFORE the target) rather than trying to
  engrave a continuous bend.

- When the English describes a register relative to the song ("high",
  "octave above the tonic"), anchor the tonic to the song's HOME
  register (octave 4 for typical vocal/treble parts), then derive
  "high" relative to that. Do not anchor the tonic to an already-high
  octave and then add another octave on top — that puts notes well
  above singable range. For vocals: tonic in octave 4, "high" is
  octave 5. Avoid octave 6+ unless the English specifically calls for
  whistle/coloratura register.

- When the snippet creates Measures explicitly, attach key signature,
  time signature, and tempo marking to the FIRST Measure, not to the
  Part. (E.g., m1.append(ks); m1.append(ts); m1.append(mm) rather than
  part.append(ks).)

- To extract the tonic from another snippet's key, find the first
  `key.Key` in the source's elements and use `.tonic` DIRECTLY. NEVER
  call `.asKey('major')` or `.asKey('minor')` on it, even via a
  re-constructed KeySignature — those silently override the source's
  mode and can return the relative-major or relative-minor tonic
  instead of the actual song tonic. Correct pattern:
    found_key = next((el for el in src.flatten()
                      if isinstance(el, key.Key)), None)
    tonic_name = found_key.tonic.name if found_key else 'E'

- Always provide a fallback for every piece of metadata you extract.
  If you check `found_ts is None`, also check `found_key is None` and
  `found_mm is None`. Fallbacks should match the song's intended
  values (e.g., E minor for the blues vault), not generic defaults
  like A minor."""


register_fragment(MUSIC_PROMPT_FRAGMENT)
