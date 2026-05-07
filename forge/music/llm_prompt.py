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

Other pre-injected globals: random, math, numpy. Do NOT `import random` —
it's already in scope. To use `copy` (e.g., copy.deepcopy), `import copy`
inside the function — that one is not pre-injected.

For music output: return a music21.stream.Stream (Score / Part / Measure / ...).
The runtime serializes it to MusicXML and the plugin renders it as engraved
notation. Do NOT return dicts of pitch/beat data — return real notes.

Composition helpers — also pre-injected as globals (do NOT import these):
  bar(*items, time_signature=, number=)  -> Measure
  voices(*streams, instruments=)         -> Score (parallel / overlay)
  sequence(*streams)                     -> Score (linear / concat)
  repeat(stream, n)                      -> Score (n copies end-to-end)
  pentatonic(key_or_tonic, mode='minor', octave_range=(4,5),
             include_blue=False)         -> list[Pitch]

These hide music21 boilerplate (part/measure assembly, deepcopy,
rest-padding). Use them rather than hand-rolling those patterns.
Idiomatic examples:

  # AAB phrase structure (composing two sub-phrases linearly)
  return sequence(repeat(phrase_a, 2), phrase_b)

  # Vocal melody over harmonic frame (parallel composition)
  return voices(form, vocal_line)

  # 12-bar blues with solo between choruses 2 and 3
  return sequence(repeat(chorus, 2), solo_chorus, chorus)

  # Build a measure with auto-rest padding
  return bar(
      note.Note('C4', quarterLength=2.0),
      note.Note('E4', quarterLength=2.0),
      time_signature=ts,
  )

  # Get a pentatonic scale (with blue note for blues)
  scale = pentatonic(found_key, mode='minor', octave_range=(4, 5),
                     include_blue=True)

Composition rules — prefer the helpers above to hand-rolled equivalents:

- For linear composition (sections played end-to-end), use sequence(...)
  — not hand-rolled measure concatenation. sequence aligns parts BY
  POSITION across inputs (input[0].parts[0] + input[1].parts[0] + ...
  becomes output.parts[0]; same for parts[1], etc.) and renumbers
  measures sequentially.

  When sections have different numbers of voices — e.g., vocal choruses
  with [harm, vocal] sit alongside an instrumental solo chorus with
  [harm, solo] — sequence auto-pads the missing voices with rest
  measures matching the input's bar count and time signature. So a
  song that mixes 2-voice and 3-voice sections produces 3 continuous
  staves automatically: each section's missing voices appear as rest
  measures in the rendered output. You do NOT need to manually build
  silent rest-filled parts for sections that don't use a given
  instrument; sequence handles that.

  CRITICAL: do NOT manually replicate voices()/sequence() by iterating
  `getElementsByClass(stream.Part)` and appending parts to a Score —
  the helpers handle deepcopy, alignment, and rest-padding correctly.
  If you find yourself walking parts yourself, stop and use the helper
  instead. Each intermediate snippet's compute should be a few lines
  ending in `return voices(...)` or `return sequence(...)`.

- For parallel composition (multiple parts playing simultaneously),
  use voices(...) — not hand-rolled part merging. Pass instruments via
  voices(s1, s2, instruments=['Voice', 'AcousticGuitar']) if you need
  to relabel parts at the composition site.

- For repeating a section, use repeat(stream, n) instead of writing
  sequence(stream, stream, ..., stream).

- For pentatonic scales, use pentatonic(key_or_tonic, mode='minor', ...)
  — don't hand-derive intervals like (0, 3, 5, 7, 10) in your own code.
  The helper returns ordered Pitch objects across the requested octave
  range; pass include_blue=True to add the b5.

- For Measures, prefer bar(*items, time_signature=ts) over manual
  Measure construction. bar() auto-pads with a trailing Rest if items
  are short and raises ValueError if they overflow — you don't have
  to compute `bar_ql - total_so_far` yourself. (Manual Measure
  construction is still appropriate when you need to attach key/time/
  tempo metadata explicitly or place elements at non-default offsets;
  the music21 rules below still apply when you do.)

Music21 idioms — common pitfalls to avoid (relevant when going below
the composition-helper layer):

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
  time signature, and tempo marking to the FIRST Measure ONLY — never
  to the Part, and never to BOTH. The pattern `part.append(ts);
  m1.append(ts)` (whether the same ts object reused or a duplicate
  created) produces redundant or conflicting metadata in the rendered
  score. Pick the first Measure. Build each metadata object once, in a
  local variable, and attach it once:
    ts = meter.TimeSignature('12/8')
    ks = key.Key('E', 'major')
    mm = tempo.MetronomeMark(number=70,
                              referent=duration.Duration(type='quarter', dots=1))
    m1.append(ks); m1.append(ts); m1.append(mm)
  Do NOT also do `part.append(ts)` or `part.append(mm)`.

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
  like A minor.

- When copying individual music21 elements (notes, rests, chords,
  chord symbols) between streams — for example, when merging measures
  from a sub-snippet's output into a new measure — use
  `copy.deepcopy(el)` after `import copy`. The `.copy()` method only
  exists on Stream subclasses; calling it on a `harmony.ChordSymbol`
  raises AttributeError. Without copying, appending the same element
  to multiple parents can cause music21 to behave unpredictably.

- Only pass arguments to `context.compute` that the callee snippet
  actually accepts. Most leaf snippets declare `def compute(context):`
  with no extra params. Inventing kwargs like `instance=1` to label
  successive calls does NOT work — the kwargs propagate to the callee
  and either raise TypeError or are silently ignored (they don't
  produce different results). To get different realizations of the
  same English from successive calls, the callee itself must be
  non-deterministic (e.g., uses `random` without a seed); kwargs at
  the call site don't change anything.

- `stream.flatten()` removes container structure (Score → Part →
  Measure → ...) and returns leaf elements (notes, rests, metadata).
  To get Parts from a Score, use `score.getElementsByClass(stream.Part)`
  directly. The chain `score.flatten().getElementsByClass(stream.Part)`
  returns nothing because flattening already discarded the Parts.

- Use `flatten()` consistently for metadata extraction — `src.flatten()`
  rather than `src.recurse()`. Both work, but consistency across snippets
  in the same vault makes them easier to read.

- Do NOT leave self-correcting "thinking out loud" comments in the
  final code. Comments like `# 1.5 + 1.0 + 0.5 = 3.0 — nope, need 6.0`
  followed by an adjustment, or `# adjust: make this 3.5 instead`,
  are scratch work that should be cleaned up before returning the code.
  Compute durations correctly the first time, or use the
  `remaining = bar_ql - total_so_far` pattern to fill remaining time
  with a Rest.

- If a snippet acts as the harmonic frame for the song (downstream
  snippets call `context.compute` on it to read key/time/tempo),
  explicitly attach ALL THREE of `key.Key(tonic, mode)`,
  `meter.TimeSignature(...)`, and `tempo.MetronomeMark(...)` to the
  first Measure of its Score. Omitting any of these forces every
  downstream snippet to use a fallback default that may not match
  the song's intended values.

- In the English facet, use `[[snippet_name]]` ONLY for forward
  dependencies — snippets this one calls via `context.compute(...)`.
  Do NOT use `[[]]` to reference parent snippets that call this one
  (e.g., a leaf phrase referencing the chorus that uses it, or a
  chorus referencing the song that contains it). Obsidian's backlinks
  panel handles upward navigation automatically; manual upward `[[]]`
  links create phantom edges in the dependency graph that don't
  match runtime calls and can mislead the LLM at generation time
  into trying to call the parent. To reference a parent in prose,
  use plain text ("the song", "the chorus") without the `[[]]`."""


register_fragment(MUSIC_PROMPT_FRAGMENT)
