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
  music21, stream, note, chord, meter, key, tempo, pitch, duration, instrument, harmony, roman.

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
  minor_pentatonic(key_or_tonic, octave_range=(4,5),
                   include_blue=False)   -> list[Pitch]
  major_pentatonic(key_or_tonic, octave_range=(4,5))
                                          -> list[Pitch]
  with_velocity(notes, pattern)           -> notes (mutated in place)

Percussion instrument factories (kit pieces with correct GM
channel-10 routing + percMapPitch — use these by preference over
raw music21 percussion classes; they wire articulation + kit-piece
distinction correctly):
  closed_hihat()  -> Instrument (GM note 42)
  open_hihat()    -> Instrument (GM note 46)
  pedal_hihat()   -> Instrument (GM note 44)
  low_tom()       -> Instrument (GM note 41)
  mid_tom()       -> Instrument (GM note 47)
  high_tom()      -> Instrument (GM note 50)
  crash_cymbal()  -> Instrument (GM note 49)
  ride_cymbal()   -> Instrument (GM note 51)

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
  scale = minor_pentatonic(found_key, octave_range=(4, 5),
                           include_blue=True)

Composition rules — prefer the helpers above to hand-rolled equivalents:

- For linear composition (sections played end-to-end), use sequence(...)
  — not hand-rolled measure concatenation. At each voice position
  across the inputs, sequence groups parts by INSTRUMENT IDENTITY:
  same-instrument parts at the same position merge into one continuous
  output stave; different-instrument parts split into separate staves
  with rest-padding for inactive sections. So
  `sequence(chorus, chorus, solo_chorus, chorus)` where each chorus
  has [Piano, Vocalist] and solo_chorus has [Piano, ElectricGuitar]
  produces three staves: Piano continuous across all four sections;
  Vocalist active in the choruses with rests during the solo;
  ElectricGuitar active during the solo with rests during choruses.
  Measures are renumbered sequentially in each output stave. Mix
  voice counts and instruments freely.

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

- For pentatonic scales, use `minor_pentatonic(key_or_tonic, ...)` or
  `major_pentatonic(key_or_tonic, ...)` — don't hand-derive intervals
  like (0, 3, 5, 7, 10) in your own code. The helpers return ordered
  Pitch objects across the requested octave range; minor accepts
  `include_blue=True` to add the b5 (the major variant does not).

  **For blues vocal/instrumental lines, use `minor_pentatonic` even
  when the source key's mode is 'major'** — the
  minor-pentatonic-over-major-progression pattern is the blues
  convention. The function name documents the choice; you do NOT
  need to write a defensive English note about "deliberate mode
  override" because there is no mode kwarg to override.

- For percussion kits, use the lib factory helpers
  (`closed_hihat()`, `open_hihat()`, `pedal_hihat()`, `low_tom()`,
  `mid_tom()`, `high_tom()`, `crash_cymbal()`, `ride_cymbal()`)
  rather than hand-configuring `instrument.HiHatCymbal()` /
  `instrument.TomTom()` etc. The factories set `percMapPitch` to
  the correct GM note number (channel 10), which is what GM
  playback uses to distinguish closed-vs-open hi-hat, low-vs-mid
  tom, etc. — music21's default class often picks a non-canonical
  GM note (e.g. HiHatCymbal defaults to GM 44 = pedal, not 42 =
  closed). The factories give predictable audible output.

  music21 has ONE `TomTom` class; the three tom factories differ
  only in `percMapPitch`. Same for hi-hat: one `HiHatCymbal` class,
  three articulations distinguished by GM note number.

  Standard percussion (`instrument.BassDrum()`, `instrument.SnareDrum()`)
  is fine without a factory — music21's defaults map correctly to
  GM Bass Drum 1 (35) and Acoustic Snare (38). Use them directly.

- For percussion (and any rhythmic content), vary note velocities to
  avoid robotic-sounding output. Use `with_velocity(notes, pattern)`
  with 'human' as a sensible default. Use 'ghost' for soft hits
  between accented hits (e.g., snare ghost notes); 'accent' for the
  loud hits that punch. Cyclic int lists like `[100, 60, 80, 60]`
  apply per-beat emphasis patterns. Default music21 velocity is 90;
  uniform 90 sounds like a drum machine. Always apply some variation
  for content where rhythm is the focus. Rests in the sequence are
  skipped automatically.

- When a piece's dynamic arc is artistically load-bearing, call
  `with_velocity(notes, profile, mark_dynamics=True)` so the dynamic
  markings appear visibly in the printed score (MuseScore via
  MusicXML), not just in MIDI playback. The flag inserts a single
  Italian dynamic mark (`pp`/`p`/`mp`/`mf`/`f`/`ff`) for int and
  named profiles, and hairpin spanners (`<` / `>`) plus bracketing
  dynamics for `'crescendo'` / `'decrescendo'`. List patterns
  (cyclic per-note variation) deliberately skip dynamic insertion —
  too granular to mark cleanly. Default is `mark_dynamics=False` for
  back-compat and for pieces (e.g., Reich-style phase music) where
  dynamics are intentionally absent.

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

- harmony.ChordSymbol takes ABSOLUTE chord-symbol notation, NOT
  Roman-numeral analysis tokens. Its `figure` attribute (or the
  string passed to the constructor) expects a root LETTER (A–G),
  optional accidental, optional quality suffix (`m`, `dim`, `aug`,
  `7`, `maj7`, `m7`, `sus4`, ...), and optional slash bass:
    "C", "G7", "Dm/F", "F#dim", "Bb", "AmM7"
  Passing a Roman numeral instead — `"I"`, `"IV"`, `"V"`, `"ii7"` —
  raises `"Chord X does not begin with a valid root note."` because
  the parser checks position 0 for {A,B,C,D,E,F,G} and the Roman
  tokens start with `I`, `V`, etc.

  Roman numerals belong to `music21.roman`; absolute chord symbols
  belong to `music21.harmony`. Don't pass one to the other.

  When a snippet's INPUT is a Roman numeral and the goal is a
  chord-symbol label above the staff, there are two acceptable
  patterns. Pick whichever the English actually asks for:

  (a) Drop the chord-symbol label entirely. Insert only the sounding
      chord whose pitches you get from RomanNumeral; the rendered
      score still shows the harmony via the noteheads, just without
      a textual label above the bar. Smallest correct fix when the
      ChordSymbol adds nothing engraved that the Chord doesn't:

        rn = roman.RomanNumeral(numeral, k)
        m.insert(0, chord.Chord(list(rn.pitches), quarterLength=bar_ql))

  (b) Convert Roman → absolute chord-symbol BEFORE assigning to
      `cs.figure`. The root letter comes from `rn.root().name`; the
      quality suffix is derived from `rn.quality` (or built from the
      Roman's intervals if you need sevenths / alterations). Minimal
      idiom for triads — "I" in E major becomes "E", "ii" becomes
      "F#m", "V" becomes "B":

        rn = roman.RomanNumeral(numeral, k)
        root_name = rn.root().name
        suffix = {"major": "", "minor": "m",
                  "diminished": "dim", "augmented": "aug"}[rn.quality]
        cs = harmony.ChordSymbol(root_name + suffix)
        cs.key = k
        m.insert(0, cs)
        m.insert(0, chord.Chord(list(rn.pitches), quarterLength=bar_ql))

      For sevenths and richer qualities, extend the suffix map
      (`"dominant-seventh"` → `"7"`, `"major-seventh"` → `"maj7"`,
      `"minor-seventh"` → `"m7"`, etc.) or build the figure string
      from `rn.figure`'s components. Verify the resulting string
      parses by passing it to `harmony.ChordSymbol(...)` rather than
      assigning to `cs.figure` after construction.

  In either pattern, do NOT round-trip through
  `cs.figure = numeral` — assigning a Roman to `figure` is the
  exact API misuse this rule exists to prevent.

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

- Avoid bend, glissando, and continuous-pitch articulations — they
  are hard to engrave reliably across renderers. When the English asks
  for a bend, prefer a discrete approach note (a grace-note-length
  pitch one scale step below the target, placed BEFORE the target)
  rather than trying to engrave a continuous bend.

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
  use plain text ("the song", "the chorus") without the `[[]]`.

- Bare `[[snippet_name]]` references from a snippet inside a library
  subdirectory resolve to siblings in the same directory FIRST, per
  v0.2.26's caller-scoped resolution. For example, a snippet at
  `forge-music/blues/song.md` writing `[[chorus]]` resolves to
  `forge-music/blues/chorus`, NOT some unrelated top-level `chorus`.
  You do NOT need to write `[[blues/chorus]]` from inside
  `blues/song.md` — bare `[[chorus]]` is sufficient and is the
  preferred form. Qualified references (`[[forge-music/some_snippet]]`,
  `[[other-library/name]]`) are still resolved as absolute paths and
  bypass caller-scope when you genuinely want a cross-directory or
  cross-library reference."""


register_fragment("music", MUSIC_PROMPT_FRAGMENT)
