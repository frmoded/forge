"""Tests for the prompt-assembly split (BASE + domain fragments)."""
from forge.core.llm_prompts import (
  BASE_SYSTEM_PROMPT,
  build_system_prompt,
  register_fragment,
  registered_fragments,
)


def test_base_prompt_has_snippet_conventions():
  # Distinctive substrings from the base prompt — should always be present.
  assert "code generator for the Forge snippet system" in BASE_SYSTEM_PROMPT
  assert "def compute(context)" in BASE_SYSTEM_PROMPT
  assert "context.compute(" in BASE_SYSTEM_PROMPT
  assert "random, math, numpy" in BASE_SYSTEM_PROMPT


def test_base_prompt_forbids_top_level_code():
  """Regression — generated snippets sometimes duplicated logic at the
  module level. The runtime only calls compute(), so the top-level block
  is dead code. The prompt must keep telling generations not to do this."""
  assert "Place ALL executable logic inside `compute`" in BASE_SYSTEM_PROMPT
  assert "Module-level statements" in BASE_SYSTEM_PROMPT


def test_base_prompt_has_no_music_specific_content():
  # Music-specific terms should have moved to the music fragment.
  assert "music21" not in BASE_SYSTEM_PROMPT
  assert "MusicXML" not in BASE_SYSTEM_PROMPT


def test_music_fragment_is_registered_after_llm_import():
  # Triggers the side-effect import chain (llm imports forge.music.llm_prompt).
  import forge.core.llm  # noqa: F401
  fragments = registered_fragments()
  assert any("music21" in f for f in fragments), \
    f"expected music fragment registered; have {fragments}"


def test_assembled_prompt_contains_base_and_music():
  import forge.core.llm  # noqa: F401  (ensure registration)
  prompt = build_system_prompt()
  # Base content
  assert "code generator for the Forge snippet system" in prompt
  assert "def compute(context)" in prompt
  # Music content
  assert "music21" in prompt
  assert "MusicXML" in prompt or "music21.stream.Stream" in prompt


def test_register_fragment_is_idempotent():
  before = len(registered_fragments())
  register_fragment("Test fragment for idempotency.")
  register_fragment("Test fragment for idempotency.")
  after = len(registered_fragments())
  assert after - before == 1


def test_assembled_prompt_is_non_empty():
  prompt = build_system_prompt()
  assert isinstance(prompt, str)
  assert len(prompt.strip()) > 0


def test_music_fragment_covers_known_pitfalls():
  """Regression — these rules were added after concrete bugs in generated
  music snippets. Removing one is almost always a mistake; test exists to
  make that an explicit conversation."""
  import forge.core.llm  # noqa: F401  (ensure registration)
  prompt = build_system_prompt()
  # MetronomeMark referent guidance
  assert "MetronomeMark" in prompt
  assert "referent" in prompt
  assert "dotted quarter" in prompt or "dots=1" in prompt
  # Instrument-on-Part
  assert "instrument" in prompt and "Piano" in prompt
  # ChordSymbol vs addLyric
  assert "ChordSymbol" in prompt
  assert "addLyric" in prompt
  # Bar duration derived from time signature
  assert "barDuration" in prompt
