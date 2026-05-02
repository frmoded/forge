import pytest
from forge.core.serialization import serialize_result


def test_passthrough_for_plain_values():
  assert serialize_result(42) == 42
  assert serialize_result("hello") == "hello"
  assert serialize_result({"a": 1}) == {"a": 1}
  assert serialize_result([1, 2, 3]) == [1, 2, 3]
  assert serialize_result(None) is None


def test_passthrough_for_dicts_with_type_key():
  # A snippet that already returns a tagged payload (e.g. {"type": "data", ...})
  # should not be re-wrapped — only music21 objects trigger serialization.
  payload = {"type": "data", "value": 7}
  assert serialize_result(payload) == payload


def _music21():
  return pytest.importorskip("music21")


def test_serializes_music21_score_to_musicxml():
  music21 = _music21()
  score = music21.stream.Score()
  part = music21.stream.Part()
  part.append(music21.note.Note("C4", quarterLength=1.0))
  score.append(part)

  result = serialize_result(score)

  assert isinstance(result, dict)
  assert result["type"] == "musicxml"
  assert isinstance(result["content"], str)
  assert "<?xml" in result["content"]
  assert "score-partwise" in result["content"] or "score-timewise" in result["content"]


def test_serializes_music21_part_to_musicxml():
  """Parts (and any Stream subclass) work, not just Scores."""
  music21 = _music21()
  part = music21.stream.Part()
  part.append(music21.note.Note("D4"))

  result = serialize_result(part)

  assert result["type"] == "musicxml"
  assert "<?xml" in result["content"]


def test_wraps_loose_note_in_stream():
  """A bare Note is wrapped in a Stream so smoke-test snippets like
  `return note.Note('D4')` work end-to-end."""
  music21 = _music21()
  n = music21.note.Note("D4")

  result = serialize_result(n)

  assert result["type"] == "musicxml"
  assert "<?xml" in result["content"]


def test_passthrough_when_music21_unavailable(monkeypatch):
  """If music21 isn't importable, plain values still pass through."""
  import sys
  monkeypatch.setitem(sys.modules, "music21", None)
  assert serialize_result(42) == 42
  assert serialize_result("plain") == "plain"


def _score_with_one_note():
  music21 = _music21()
  s = music21.stream.Score()
  p = music21.stream.Part()
  p.append(music21.note.Note("C4"))
  s.append(p)
  return s


def test_title_falls_back_to_snippet_id():
  s = _score_with_one_note()
  snippet = {"meta": {}, "snippet_id": "authoring/weary_blues_line"}
  result = serialize_result(s, snippet)
  assert "weary_blues_line" in result["content"]
  assert "Music21 Fragment" not in result["content"]


def test_title_uses_explicit_frontmatter_title():
  s = _score_with_one_note()
  snippet = {
    "meta": {"title": "Weary Blues Line", "description": "ignored"},
    "snippet_id": "authoring/weary_blues_line",
  }
  result = serialize_result(s, snippet)
  assert "Weary Blues Line" in result["content"]


def test_description_does_not_become_title():
  """Description is for docs; renaming the snippet should change the rendered title."""
  s = _score_with_one_note()
  snippet = {
    "meta": {"description": "Opening line — should not appear as title."},
    "snippet_id": "authoring/song_renamed",
  }
  result = serialize_result(s, snippet)
  assert "song_renamed" in result["content"]
  assert "should not appear" not in result["content"]


def test_title_left_alone_when_no_snippet_provided():
  s = _score_with_one_note()
  result = serialize_result(s)
  # music21's default still wins when we don't pass a snippet.
  assert "Music21 Fragment" in result["content"]
