"""Tests for forge.core.llm helpers that don't need an actual LLM call."""
from forge.core.llm import _find_deps


def test_find_deps_picks_up_real_wikilinks():
  body = "See also [[chorus]] and [[song]]."
  assert _find_deps(body) == ["chorus", "song"]


def test_find_deps_handles_aliased_wikilinks():
  body = "Discussed in [[song|the song]]."
  assert _find_deps(body) == ["song"]


def test_find_deps_picks_up_qualified_ids():
  body = 'context.compute("forge/registry/lookup")'
  assert _find_deps(body) == ["forge/registry/lookup"]


def test_find_deps_skips_prose_placeholders():
  """Prose like '[[<vault_name>/...]]' in English / docstrings or f-strings
  like '[[{vault_name}/...]]' are documentation, not snippet refs. They were
  triggering recursive /generate to 404 on phantom deps before the regex got
  tightened to require valid ID chars only."""
  body = (
    "After install, try [[<vault_name>/...]] to invoke any of its snippets."
  )
  assert _find_deps(body) == []


def test_find_deps_skips_curly_brace_placeholders():
  body = 'message = f"now try [[{vault_name}/...]] to invoke."'
  assert _find_deps(body) == []


def test_find_deps_dedups_repeats():
  body = "[[chorus]] then [[chorus]] again."
  assert _find_deps(body) == ["chorus"]


def test_find_deps_combines_wikilink_and_compute():
  body = '[[chorus]] then context.compute("forge/registry/lookup")'
  assert _find_deps(body) == ["chorus", "forge/registry/lookup"]
