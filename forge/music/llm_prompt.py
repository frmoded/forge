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


MUSIC_PROMPT_FRAGMENT = """Music21 modules in scope (do NOT import them):
  music21, stream, note, chord, meter, key, tempo, pitch, duration, instrument.

For music output: return a music21.stream.Stream (Score / Part / Measure / ...).
The runtime serializes it to MusicXML and the plugin renders it as engraved
notation. Do NOT return dicts of pitch/beat data — return real notes."""


register_fragment(MUSIC_PROMPT_FRAGMENT)
