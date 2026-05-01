"""Serialize snippet return values into wire-shippable shapes.

Snippets stay clean (just `return score`); the runtime turns rich domain
objects into self-describing tagged payloads that the plugin can dispatch
on by `result.type`.

Plain values (str, int, dict, list, etc.) pass through untouched.
"""


def serialize_result(value):
  """Turn a snippet's return value into something wire-shippable.

  Adds a new dispatch by importing lazily and checking isinstance — adding
  IFC/SVG/etc. later is a matter of dropping another block in here.
  """
  musicxml = _try_serialize_music21(value)
  if musicxml is not None:
    return musicxml

  # (Future) IFC objects → IFC string
  # (Future) Drawing objects → SVG string

  return value


def _try_serialize_music21(value):
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

  from music21.musicxml.m21ToXml import GeneralObjectExporter
  xml_bytes = GeneralObjectExporter(value).parse()
  return {
    "type": "musicxml",
    "content": xml_bytes.decode("utf-8"),
  }
