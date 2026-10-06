"""Lean-edition message (drain 2026-10-05-2330, CCQA finding R1).

On the Lean edition the music21 wheel is never mounted, so telling the user "music21 is not yet mounted ...
please wait for the wheel to finish loading and retry" is a dead end (CCQA waited ~25 s and retried: same
result). The plugin now sets FORGE_EDITION in the Pyodide runtime ("lean" | "music"); _require_music21 reads it
to tell "this edition does not include music21" from "music21 is still loading". The genuine still-loading case
keeps its existing "wait" message; music21 being present means no error whatever the flag says."""
import pytest

from forge.music import lib

WAIT = "music21 is not yet mounted"


@pytest.fixture
def no_music21(monkeypatch):
  """The runtime state with music21 absent: the sentinel names are None."""
  monkeypatch.setattr(lib, "note", None)
  monkeypatch.setattr(lib, "stream", None)


def _message(monkeypatch=None):
  with pytest.raises(RuntimeError) as e:
    lib._require_music21()
  return str(e.value)


def test_lean_edition_says_music_is_not_included_and_names_the_music_edition(no_music21, monkeypatch):
  monkeypatch.setenv("FORGE_EDITION", "lean")
  msg = _message()
  assert "Lean edition" in msg
  assert "Music edition" in msg
  assert "not included" in msg


def test_lean_message_does_not_tell_the_user_to_wait_or_retry(no_music21, monkeypatch):
  monkeypatch.setenv("FORGE_EDITION", "lean")
  msg = _message().lower()
  for stale_advice in ("wait", "few seconds", "retry", "not yet mounted", "finish loading"):
    assert stale_advice not in msg, stale_advice


def test_lean_message_is_one_or_two_plain_sentences(no_music21, monkeypatch):
  monkeypatch.setenv("FORGE_EDITION", "lean")
  msg = _message()
  assert 1 <= msg.count(". ") + 1 <= 2 and len(msg) < 220, msg


@pytest.mark.parametrize("value", ["music", "", "Lean", "LEAN", "other", " lean"])
def test_any_non_lean_value_keeps_the_existing_wait_message(no_music21, monkeypatch, value):
  monkeypatch.setenv("FORGE_EDITION", value)
  msg = _message()
  assert WAIT in msg and "retry" in msg.lower()
  assert "Lean edition" not in msg


def test_flag_unset_keeps_the_existing_wait_message(no_music21, monkeypatch):
  monkeypatch.delenv("FORGE_EDITION", raising=False)
  msg = _message()
  assert WAIT in msg and "retry" in msg.lower()
  assert "Lean edition" not in msg


@pytest.mark.parametrize("flag", ["lean", "music", None])
def test_music21_present_is_never_an_error_whatever_the_flag_says(monkeypatch, flag):
  if flag is None:
    monkeypatch.delenv("FORGE_EDITION", raising=False)
  else:
    monkeypatch.setenv("FORGE_EDITION", flag)
  monkeypatch.setattr(lib, "note", object())
  monkeypatch.setattr(lib, "stream", object())
  assert lib._require_music21() is None


@pytest.mark.parametrize("missing", ["note", "stream"])
def test_either_sentinel_missing_counts_as_absent(monkeypatch, missing):
  monkeypatch.setenv("FORGE_EDITION", "lean")
  monkeypatch.setattr(lib, "note", object())
  monkeypatch.setattr(lib, "stream", object())
  monkeypatch.setattr(lib, missing, None)
  assert "Lean edition" in _message()


def test_a_chip_called_on_lean_raises_the_lean_message_not_a_raw_error(no_music21, monkeypatch):
  """User-facing contract: through a real chip entry point, not just the helper."""
  monkeypatch.setenv("FORGE_EDITION", "lean")
  for call in (lambda: lib.bar(), lambda: lib.kick(), lambda: lib.rhythm_data_to_stream({})):
    with pytest.raises(RuntimeError) as e:
      call()
    assert "Lean edition" in str(e.value), str(e.value)


def test_the_chip_that_validates_before_touching_music21_still_names_its_own_error(no_music21, monkeypatch):
  """accent_mask is pure data (no music21): its own ValueError must not be swallowed by the lean message."""
  monkeypatch.setenv("FORGE_EDITION", "lean")
  with pytest.raises(ValueError, match="accent_mask"):
    lib.accent_mask({}, {})
