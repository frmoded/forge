"""Serialize snippet return values into wire-shippable shapes.

Snippets stay clean (just `return score`); the runtime turns rich domain
objects into self-describing tagged payloads that the plugin can dispatch
on by `result.type`.

Plain values (str, int, dict, list, etc.) pass through untouched.
"""


def serialize_result(value, snippet=None):
  """Turn a snippet's return value into something wire-shippable.

  `snippet` is the resolved snippet dict (meta/body/snippet_id/...); used by
  format-specific serializers that want metadata like a title.
  """
  musicxml = _try_serialize_music21(value, snippet)
  if musicxml is not None:
    return musicxml

  # (Future) IFC objects → IFC string
  # (Future) Drawing objects → SVG string

  return value


def _try_serialize_music21(value, snippet):
  """Return a tagged MusicXML payload if value is a music21 object, else None."""
  try:
    import music21
  except ImportError:
    return None

  # Accept any Stream subclass (Score, Part, Measure, ...) and wrap loose
  # Music21Objects (Note, Chord, Rest) in a Stream so simple smoke tests work.
  if isinstance(value, music21.base.Music21Object) and not isinstance(value, music21.stream.Stream):
    s = music21.stream.Stream()
    s.append(value)
    value = s

  if not isinstance(value, music21.stream.Stream):
    return None

  _set_score_title(value, snippet)

  from music21.musicxml.m21ToXml import GeneralObjectExporter
  xml_bytes = GeneralObjectExporter(value).parse()
  return {
    "type": "musicxml",
    "content": xml_bytes.decode("utf-8"),
  }


def _set_score_title(stream_, snippet):
  """Override music21's "Music21 Fragment" default with snippet metadata.

  Title precedence: explicit `title:` in frontmatter, else the bare snippet
  ID (filename). Description is intentionally not used — it's for docs, not
  display, and renaming a snippet should change the rendered title.
  """
  if snippet is None:
    return
  meta = snippet.get("meta") or {}
  title = meta.get("title") or _bare_id(snippet.get("snippet_id"))
  if not title:
    return
  import music21
  if stream_.metadata is None:
    stream_.insert(0, music21.metadata.Metadata())
  stream_.metadata.title = str(title).strip()


def _bare_id(snippet_id):
  if not snippet_id:
    return None
  return snippet_id.rsplit("/", 1)[-1]
