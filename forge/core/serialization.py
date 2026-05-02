"""Serialize snippet return values into wire-shippable shapes.

Snippets stay clean (just `return score`); the runtime turns rich domain
objects into self-describing tagged payloads that the plugin can dispatch
on by `result.type`.

Plain values (str, int, dict, list, etc.) pass through untouched.

Also provides wire-format helpers used by snapshot capture/read:
  serialize_for_wire(value, snippet)  -> (content_type, content_str)
  deserialize_from_wire(content_type, content_str) -> python value
"""

import json

# Tagged dicts coming back from serialize_result whose `type` is one of these
# are treated as native wire formats — body becomes their `content` field.
_NATIVE_WIRE_FORMATS = {"musicxml"}


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


def serialize_for_wire(value, snippet=None):
  """Reduce a python value to (content_type, content_str) for storage.

  - Tagged payloads from serialize_result (e.g. {type: musicxml, content: ...})
    decompose into (their type, their content).
  - Everything else round-trips through JSON. Strings, numbers, dicts, lists,
    None — all become content_type='json' with json.dumps(value) as body.
  """
  payload = serialize_result(value, snippet)
  if isinstance(payload, dict) and payload.get("type") in _NATIVE_WIRE_FORMATS:
    return payload["type"], payload["content"]
  return "json", json.dumps(payload)


def deserialize_from_wire(content_type, content_str):
  """Inverse of serialize_for_wire. Used for data snippet reads and frozen
  snapshot reads."""
  if content_type == "json":
    return json.loads(content_str)
  if content_type == "text":
    return content_str
  if content_type == "musicxml":
    import music21
    return music21.converter.parseData(content_str, format="musicxml")
  raise ValueError(f"unsupported content_type: {content_type!r}")


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
