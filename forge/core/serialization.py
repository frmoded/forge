"""Serialize snippet return values into wire-shippable shapes.

Snippets stay clean (just `return score`); the runtime turns rich domain
objects into self-describing tagged payloads that the plugin can dispatch
on by `result.type`.

Plain values (str, int, dict, list, etc.) pass through untouched.

Also provides wire-format helpers used by snapshot capture/read:
  serialize_for_wire(value, snippet)  -> (content_type, content_str)
  deserialize_from_wire(content_type, content_str) -> python value

Content_types come in two families. Text types (json, yaml, text, markdown,
svg, musicxml) carry their content inline in the snippet body and deserialize
to native python values (dict / str / music21 Stream). Binary types
(image/jpeg, image/png, audio/mpeg, audio/wav, video/mp4) live in a sibling
asset file referenced by `content_ref` in frontmatter; read_data_snippet
returns them as a (bytes, content_type) tuple so callers can decide what to
do with the payload.
"""

import dataclasses
import importlib
import json

import numpy


# Tag keys used by the codec. Picked to be unmistakably-internal so user
# data dicts won't collide with the deserializer's class-lookup branch.
#   Format (dataclass): {"__dataclass__": "qualified.ClassName", "fields": {...}}
#   Format (ndarray):   {"__ndarray__": true, "dtype": "...", "shape": [...], "data": [...]}
_DC_TAG = "__dataclass__"
_ND_TAG = "__ndarray__"


def _dataclass_to_jsonable(value):
  """Walk `value`, wrapping each dataclass instance and each numpy.ndarray
  in a tagged dict so the whole structure is JSON-encodable. Containers
  (list/tuple/dict) are recursed into; tuples become lists (JSON has no
  tuple). Other types pass through; non-JSON-friendly leaves (music21
  streams, object-dtype ndarrays containing non-JSON elements, etc.) will
  still raise at json.dumps time and the caller (snapshot capture) will
  warn and skip — same contract as before this codec landed.
  """
  if dataclasses.is_dataclass(value) and not isinstance(value, type):
    cls = type(value)
    return {
      _DC_TAG: f"{cls.__module__}.{cls.__qualname__}",
      "fields": {
        f.name: _dataclass_to_jsonable(getattr(value, f.name))
        for f in dataclasses.fields(value)
      },
    }
  if isinstance(value, numpy.ndarray):
    # tolist() rather than base64 bytes: snapshot files stay readable +
    # diff-able in the vault's .forge/edges store, and at the particle
    # counts we encode (sub-megabyte snapshots) the size cost is fine.
    # tolist() preserves nested rank for multi-D arrays, so we just store
    # shape alongside as a defensive cross-check on decode.
    return {
      _ND_TAG: True,
      "dtype": str(value.dtype),
      "shape": list(value.shape),
      "data": value.tolist(),
    }
  if isinstance(value, dict):
    return {k: _dataclass_to_jsonable(v) for k, v in value.items()}
  if isinstance(value, (list, tuple)):
    return [_dataclass_to_jsonable(v) for v in value]
  return value


def _jsonable_to_dataclass(value):
  """Inverse of _dataclass_to_jsonable. Rebuilds dataclass instances by
  importing the class via its stored qualified name and calling Cls(**fields),
  and rebuilds numpy.ndarray from the (dtype, shape, data) triple. Unknown
  classes raise ValueError — callers (snapshot read paths) catch the cycle
  higher up and fall back to live recomputation if needed."""
  if isinstance(value, dict):
    if _DC_TAG in value:
      qname = value[_DC_TAG]
      module_name, _, class_name = qname.rpartition(".")
      try:
        cls = getattr(importlib.import_module(module_name), class_name)
      except (ImportError, AttributeError) as e:
        raise ValueError(f"cannot resolve dataclass {qname!r}: {e}")
      kwargs = {
        k: _jsonable_to_dataclass(v) for k, v in value.get("fields", {}).items()
      }
      return cls(**kwargs)
    if value.get(_ND_TAG) is True:
      dtype = value.get("dtype")
      shape = value.get("shape") or []
      data = value.get("data")
      arr = numpy.array(data, dtype=dtype)
      # .reshape() is defensive: tolist()/array() preserve nesting for
      # numeric dtypes, but an explicit reshape catches the empty-array
      # edge case (shape=[0] with data=[]) where numpy.array(data) would
      # default to dtype=float64 of shape (0,) regardless of the rank we
      # encoded — and a future encoder change that flattens wouldn't
      # silently lose rank either.
      return arr.reshape(shape)
    return {k: _jsonable_to_dataclass(v) for k, v in value.items()}
  if isinstance(value, list):
    return [_jsonable_to_dataclass(v) for v in value]
  return value

# Tagged dicts coming back from serialize_result whose `type` is one of these
# are treated as native wire formats — body becomes their `content` field.
# moda_sim_state carries the row-oriented Particle list the iframe already
# knows how to render; same shape as /moda/compute's response, just emitted
# from generic /compute now too.
_NATIVE_WIRE_FORMATS = {"musicxml", "moda_sim_state"}

# Text content_types: payload is a string in the snippet body. deserialize_text
# returns the native python value (json -> dict/list, yaml -> dict/list/etc.,
# text/markdown/svg -> str, musicxml -> music21.stream.Stream).
TEXT_CONTENT_TYPES = ("json", "yaml", "text", "markdown", "musicxml", "svg")

# Binary content_types: payload is raw bytes in a sibling asset file pointed
# to by `content_ref` in the snippet frontmatter. deserialize_binary returns
# (bytes, content_type) so callers can dispatch on the MIME type without
# guessing from magic bytes.
BINARY_CONTENT_TYPES = (
  "image/jpeg",
  "image/png",
  "audio/mpeg",
  "audio/wav",
  "video/mp4",
)

# Bare-name aliases for backward compatibility with hand-authored vaults that
# predate the MIME-typed names. Any new authoring should use the canonical
# binary form.
_LEGACY_ALIASES = {"jpeg": "image/jpeg"}

# Exposed via /connect so the plugin's "Create new snippet" dropdown stays in
# sync with the backend. Text first, binary after — the dropdown shows them
# in this order.
SUPPORTED_CONTENT_TYPES = TEXT_CONTENT_TYPES + BINARY_CONTENT_TYPES


def _normalize(content_type: str) -> str:
  return _LEGACY_ALIASES.get(content_type, content_type)


def is_text_content_type(content_type: str) -> bool:
  return _normalize(content_type) in TEXT_CONTENT_TYPES


def is_binary_content_type(content_type: str) -> bool:
  return _normalize(content_type) in BINARY_CONTENT_TYPES


def serialize_result(value, snippet=None):
  """Turn a snippet's return value into something wire-shippable.

  Dispatch order:
  1. Already-tagged native-wire-format dicts pass through unchanged
     (idempotency — repeated calls on the same value are no-ops).
  2. Domain-specific recognizers (music21 score → musicxml,
     ParticleState → moda_sim_state). Each returns a tagged
     {type, content} dict or None.
  3. Generic fallthrough: encode dataclasses + ndarrays via
     _dataclass_to_jsonable so the result is JSON-able. Mirrors
     what serialize_for_wire does on the snapshot-capture path, so
     a value the snapshot path successfully captures also serializes
     cleanly over the /compute HTTP response.

  `snippet` is the resolved snippet dict (meta/body/snippet_id/...);
  used by format-specific serializers that want metadata like a
  title for the rendered MusicXML.
  """
  # (1) Already-tagged — pass through. Lets callers (e.g.
  # serialize_for_wire) re-feed the output without rewrapping.
  if (isinstance(value, dict)
      and value.get("type") in _NATIVE_WIRE_FORMATS):
    return value

  # (2) Domain-specific recognizers.
  musicxml = _try_serialize_music21(value, snippet)
  if musicxml is not None:
    return musicxml

  particle_state = _try_serialize_particle_state(value, snippet)
  if particle_state is not None:
    return particle_state

  # (Future) IFC objects → IFC string
  # (Future) Drawing objects → SVG string

  # (3) Generic fallthrough.
  return _dataclass_to_jsonable(value)


def serialize_for_wire(value, snippet=None):
  """Reduce a python value to (content_type, content_str) for snapshot
  storage. DIFFERENT contract from serialize_result, which produces
  the HTTP-response shape:

  - serialize_result: emit the shape the consumer wants to render
    (e.g. moda_sim_state's row-oriented Particle list for the
    iframe). May be lossy w.r.t. the original value.
  - serialize_for_wire: emit a shape the snapshot reader can
    losslessly rebuild via deserialize_text. Must round-trip back
    to the same python value.

  These coincide for music21 (musicxml deserializes back to the
  music21 Stream) but diverge for ParticleState — the row-oriented
  moda_sim_state shape drops internal fields (headings, speeds,
  width, height) that the dataclass round-trip needs. So
  serialize_for_wire takes its own route through the music21
  recognizer (round-trip-safe wire shape) and the dataclass+
  ndarray codec (round-trip-safe lossless JSON).
  """
  musicxml = _try_serialize_music21(value, snippet)
  if musicxml is not None:
    return "musicxml", musicxml["content"]

  return "json", json.dumps(_dataclass_to_jsonable(value))


def deserialize_text(content_type, content_str):
  """Deserialize a text content_type body to its native python value.
  Binary content_types must go through deserialize_binary instead."""
  ct = _normalize(content_type)
  if ct == "json":
    return _jsonable_to_dataclass(json.loads(content_str))
  if ct == "yaml":
    import yaml
    return yaml.safe_load(content_str)
  if ct in ("text", "markdown", "svg"):
    return content_str
  if ct == "musicxml":
    import music21
    return music21.converter.parseData(content_str.strip(), format="musicxml")
  raise ValueError(f"unsupported text content_type: {content_type!r}")


def deserialize_binary(content_type, content_bytes):
  """Return (bytes, content_type) for a binary content_type's payload.

  The tuple shape is the public contract: callers receive raw bytes plus the
  MIME content_type so they can dispatch (write to disk, send over HTTP,
  decode with a format-specific lib) without guessing from magic bytes. This
  mirrors how HTTP clients model binary responses.

  Snippets that consume a binary data snippet via context.compute should
  unpack at the call site:
    data, ct = context.compute("cat_reference")
  """
  ct = _normalize(content_type)
  if ct not in BINARY_CONTENT_TYPES:
    raise ValueError(f"not a binary content_type: {content_type!r}")
  if not isinstance(content_bytes, (bytes, bytearray)):
    raise TypeError(
      f"deserialize_binary expects bytes for content_type={content_type!r}, "
      f"got {type(content_bytes).__name__}"
    )
  return (bytes(content_bytes), ct)


def deserialize_from_wire(content_type, content_str):
  """Back-compat shim. Snapshot reads still use this; data snippet reads go
  through deserialize_text / deserialize_binary directly via
  read_data_snippet, which decides based on content_ref / content_type."""
  if is_binary_content_type(content_type):
    # Frozen snapshots of a binary value would carry base64-encoded bytes.
    # No first-party path captures these today (snapshot capture for a
    # binary tuple raises and _capture_edge skips), but we decode for
    # parity if a hand-written one ever shows up.
    import base64
    return deserialize_binary(content_type, base64.b64decode(content_str))
  return deserialize_text(content_type, content_str)


def _try_serialize_particle_state(value, snippet):
  """Detect a moda ParticleState dataclass and emit the iframe wire
  shape: {type: "moda_sim_state", content: {tick, particles:
  list[{id, type, x, y, mass}]}}. Returns None for non-matches so
  the caller falls through to other serializers.

  Use-time import keeps `forge.core.serialization` independent of
  `forge.moda.types` at module-load time — avoids a circular import
  if forge.moda.types ever needs core helpers. ImportError swallowed
  so environments without the moda module (or future installations
  that strip it) still load core serialization fine.

  The row-oriented transposition is intentionally duplicated from
  forge.api.moda._serialize_particles — pulling it into core would
  improve layering (the row-shape conversion is a serializer concern,
  not a router concern) but widen this prompt's blast radius. Flagged
  as a follow-up in the feedback.
  """
  try:
    from forge.moda.types import ParticleState
  except ImportError:
    return None
  if not isinstance(value, ParticleState):
    return None

  particles = [
    {
      "id": int(value.ids[i]),
      "type": str(value.types[i]),
      "x": float(value.xs[i]),
      "y": float(value.ys[i]),
      "mass": str(value.masses[i]),
    }
    for i in range(len(value.ids))
  ]
  return {
    "type": "moda_sim_state",
    "content": {"tick": int(value.tick), "particles": particles},
  }


def _normalize_percussion_display_pitches(value):
  """v0.2.216 — Return a copy of `value` with percussion-Part Note
  pitches normalized to display-appropriate positions for visual
  MusicXML serialization.

  Background: lib.play_at_beats + play_at_offsets stamp each Note's
  pitch.midi to the Part's instrument percMapPitch (kick=35=B1,
  snare=38=D2, closed-hi-hat=42=F#2, etc.) so streamToMidiFile fires
  the right channel-10 drum slot — the v0.2.159 bongo-wall fix.
  Those literal pitches render BELOW the bass staff in MusicXML
  multi-staff output, which cohort sees as "the score is an octave
  or two too low."

  This helper deep-copies the score and replaces each percussion
  Note's pitch with the kit-notation display position (kick→F4,
  snare→C5, hi-hat→G5, etc.). Verovio renders each Part on its own
  staff at a treble-clef-readable position. Original `value` stays
  untouched so the MIDI export path keeps its percMapPitch routing.

  Non-percussion Parts (and non-Score input) pass through unchanged.
  """
  try:
    import music21
    from music21 import note as _note, stream as _stream, pitch as _pitch
    from forge.music.lib import _kit_lookup
  except ImportError:
    return value
  if not isinstance(value, music21.stream.Stream):
    return value
  import copy as _copy
  display = _copy.deepcopy(value)
  parts: list = []
  if isinstance(display, music21.stream.Score):
    parts = list(display.getElementsByClass(_stream.Part))
  elif isinstance(display, music21.stream.Part):
    parts = [display]
  for part in parts:
    inst = part.getInstrument(returnDefault=False)
    if inst is None:
      continue
    info = _kit_lookup(inst)
    if info is None:
      continue
    display_name, _voice, _notehead = info
    try:
      display_midi = _pitch.Pitch(display_name).midi
    except Exception:
      continue
    for n in part.recurse().notes:
      if isinstance(n, _note.Note):
        try:
          n.pitch.midi = display_midi
        except Exception:
          pass
  return display


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
  # v0.2.216 — normalize percussion-Part Note pitches for VISUAL
  # multi-staff display. lib.play_at_beats + play_at_offsets stamp
  # pitch.midi = percMapPitch (kick=35=B1, snare=38=D2, hi-hat=42=F#2,
  # etc.) so streamToMidiFile fires the right channel-10 drum slot
  # (per the v0.2.159 bongo-wall fix). But those pitches render WAY
  # below the staff in MusicXML — the driver hit this on the v0.2.215
  # smoke ("octave or two too low"). Build a separate display copy
  # with each percussion Part's notes lifted to a treble-staff-
  # readable position (kick→F4, snare→C5, closed-hi-hat→G5, etc. —
  # same map the kit_notation transform uses for compact display).
  # Original `value` is unchanged → MIDI export downstream still gets
  # the percMapPitch routing it needs.
  display_value = _normalize_percussion_display_pitches(value)
  xml_bytes = GeneralObjectExporter(display_value).parse()
  multi_staff_xml = xml_bytes.decode("utf-8")

  # v0.2.150 — dual-XML production for percussion scores. When the
  # value is a Score with at least one UnpitchedPercussion Part, also
  # serialize a kit-notation fold so the plugin's Forge Output pane
  # can offer the multi-staff ↔ kit toggle. Backward-compat: `content`
  # remains the multi-staff XML (legacy plugin codepaths render it
  # unchanged); new fields `has_percussion` + `multi_staff_content` +
  # `kit_content` opt new plugin codepaths into the toggle.
  has_perc = False
  kit_xml = None
  multi_staff_midi_b64 = None
  if isinstance(value, music21.stream.Score):
    try:
      from forge.music.lib import has_percussion, to_kit_notation
      has_perc = has_percussion(value)
      if has_perc:
        kit_score = to_kit_notation(value)
        _set_score_title(kit_score, snippet)
        kit_bytes = GeneralObjectExporter(kit_score).parse()
        kit_xml = kit_bytes.decode("utf-8")
    except Exception:
      # Defensive: if to_kit_notation raises (unexpected music21
      # shape), drop back to multi-staff-only output. Caller still
      # gets a renderable score — just no toggle.
      has_perc = False
      kit_xml = None
    # v0.2.157 — direct music21 MIDI export for percussion. Pre-v0.2.157
    # the plugin used Verovio's renderToMIDI to generate audio bytes
    # from multi_staff_xml. Driver smoke against v0.2.156 (with audio
    # diagnostic) showed every percussion note routing to MIDI pitch 60
    # (High Bongo on channel 10) regardless of the underlying instrument
    # — Verovio falls back to the default display pitch for Unpitched
    # notes instead of honoring per-Part <midi-unpitched>NN</midi-
    # unpitched> from the MusicXML's <midi-instrument> block. music21's
    # streamToMidiFile renders the same Score directly to standard MIDI
    # with correct per-Part channel-10 routing + correct percMapPitch
    # (kick=35, snare=38, hi-hat=44 default / 42 closed / 46 open, etc.)
    # so SoundFont drums fire the right samples.
    #
    # Emitted only when the score has percussion (toggle is offered).
    # The plugin sees `multi_staff_midi_base64` in the payload and uses
    # it as the player's MIDI source — bypassing Verovio's incorrect
    # MIDI rendering. Verovio still renders the SVG + timeMap (display +
    # highlight tracking unchanged).
    if has_perc:
      try:
        from music21 import midi as _m21midi, note as _note, stream as _stream
        import io as _io
        import base64 as _b64
        import copy as _copy
        # v0.2.158/v0.2.159 — normalize percussion-Part Note pitches to
        # each part instrument's percMapPitch BEFORE MIDI export.
        # forge-music's percussion snippets (solitary, companions,
        # gathering, etc.) build kicks + hi-hats as
        # `note.Note('C4', quarterLength=...)` — pitched notes spelled at
        # C4 = MIDI pitch 60 — attached to a Part whose Instrument is
        # one of the lib.py percussion factories. music21's MIDI export
        # correctly puts these on channel 10 (drum) but uses the note's
        # spelled MIDI pitch (60 = High Bongo) NOT the Part instrument's
        # percMapPitch. Result: every kick/snare/hi-hat hit broadcasts
        # on the same drum slot. Driver smoke against v0.2.158 confirmed
        # this: 394 notes, all pitch=60, all channel 10 = bongo wall.
        #
        # Deep-copying the Score and rewriting each Note's
        # pitch.midi to the Part Instrument's percMapPitch gives music21
        # the right pitch byte to emit per NOTE_ON event. The original
        # Score (used for multi_staff_xml + kit_xml + display) is not
        # mutated. Notes already constructed as note.Unpitched (which
        # pull pitch from instrument percMap natively) are unaffected.
        _midi_score = _copy.deepcopy(value)
        for _part in _midi_score.getElementsByClass(_stream.Part):
          _inst = _part.getInstrument(returnDefault=False)
          if _inst is None:
            continue
          _pmp = getattr(_inst, "percMapPitch", None)
          if _pmp is None:
            continue
          for _n in _part.recurse().notes:
            if isinstance(_n, _note.Note):
              try:
                _n.pitch.midi = _pmp
              except Exception:
                pass
        _mf = _m21midi.translate.streamToMidiFile(_midi_score)
        _buf = _io.BytesIO()
        _mf.openFileLike(_buf)
        _mf.write()
        _midi_bytes = _buf.getvalue()
        _mf.close()
        multi_staff_midi_b64 = _b64.b64encode(_midi_bytes).decode("ascii")
      except Exception:
        multi_staff_midi_b64 = None

  payload = {
    "type": "musicxml",
    "content": multi_staff_xml,
  }
  if has_perc and kit_xml is not None:
    payload["has_percussion"] = True
    payload["multi_staff_content"] = multi_staff_xml
    payload["kit_content"] = kit_xml
    if multi_staff_midi_b64 is not None:
      payload["multi_staff_midi_base64"] = multi_staff_midi_b64
  else:
    payload["has_percussion"] = False
  return payload


def _set_score_title(stream_, snippet):
  """Override music21's "Music21 Fragment" default with snippet metadata.

  Title precedence: explicit `title:` in frontmatter, else the bare snippet
  ID (filename). Description is intentionally not used — it's for docs, not
  display, and renaming a snippet should change the rendered title.

  Also strips music21's default composer + software credits so MuseScore
  (and other renderers) don't display a "Music21" watermark in the top-
  right of the rendered score. Cohort-facing scores should show the
  cohort's title alone.
  """
  import music21
  if stream_.metadata is None:
    stream_.insert(0, music21.metadata.Metadata())

  # Set title if we have snippet metadata.
  if snippet is not None:
    meta = snippet.get("meta") or {}
    title = meta.get("title") or _bare_id(snippet.get("snippet_id"))
    if title:
      stream_.metadata.title = str(title).strip()

  # Scrub music21's default self-attribution. `composer` renders as a
  # top-right credit in MuseScore + Verovio; `software` renders as a
  # footer in some SVG paths. Either can look like "Music21" in the
  # output. Setting to empty string suppresses both cleanly.
  try:
    stream_.metadata.composer = ""
  except Exception:
    pass
  try:
    stream_.metadata.software = []
  except Exception:
    pass


def _bare_id(snippet_id):
  if not snippet_id:
    return None
  return snippet_id.rsplit("/", 1)[-1]
