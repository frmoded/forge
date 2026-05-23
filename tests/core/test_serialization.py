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


# ---------------------------------------------------------------------------
# Dataclass codec round-trip (`__dataclass__`-tagged JSON)
#
# Added after the moda integration started capturing snapshots whose return
# values were Particle / ParticleState dataclasses — json.dumps used to
# silently TypeError on those and the (then) silent skip in
# _capture_edge meant we shipped two missing edges before noticing.
# That silent-skip branch is gone as of the C7/A7 tightening — capture
# now raises SnapshotCaptureError on unserializable returns unless the
# snippet opts out — but the codec extensions below remain the right
# fix for first-class ParticleState capture.
# ---------------------------------------------------------------------------

from forge.core.serialization import serialize_for_wire, deserialize_from_wire
from forge.moda.types import Particle, ParticleState


import numpy as np


def _state(n=3, tick=0, w=800.0, h=600.0, ink=0):
  """Build a Phase-7-shape ParticleState with `n` water rows followed by
  `ink` ink rows. Per-particle fields are parallel numpy arrays; the
  index identifies one row across them."""
  total = n + ink
  ids = np.arange(total, dtype=np.int64)
  types = np.array(["water"] * n + ["ink"] * ink, dtype=object)
  xs = np.arange(total, dtype=np.float64)
  ys = np.arange(total, dtype=np.float64) * 2.0
  headings = np.full(total, 0.5, dtype=np.float64)
  speeds = np.full(total, 10.0, dtype=np.float64)
  masses = np.array(["medium"] * total, dtype=object)
  return ParticleState(
    tick=tick, ids=ids, types=types, xs=xs, ys=ys,
    headings=headings, speeds=speeds, masses=masses,
    width=w, height=h,
  )


def _assert_state_equal(a, b):
  """ParticleState equality on the arrays-first shape — the default
  __eq__ would compare arrays element-wise and raise ValueError on
  truthiness, so unpack the fields and compare each one."""
  assert a.tick == b.tick
  assert a.width == b.width
  assert a.height == b.height
  for f in ("ids", "types", "xs", "ys", "headings", "speeds", "masses"):
    assert np.array_equal(getattr(a, f), getattr(b, f)), f
    assert getattr(a, f).dtype == getattr(b, f).dtype, f
    assert getattr(a, f).shape == getattr(b, f).shape, f


def test_single_dataclass_round_trips():
  p = Particle(id=1, type="water", x=10.5, y=20.5,
               heading=1.5, speed=50.0, mass="medium")
  ct, body = serialize_for_wire(p)
  assert ct == "json"
  back = deserialize_from_wire(ct, body)
  assert isinstance(back, Particle)
  assert back == p


def test_particle_state_with_arrays_round_trips():
  """Phase 7: ParticleState now stores its per-particle fields as parallel
  numpy arrays. The dataclass codec recurses into each field; the ndarray
  codec then encodes each array as a __ndarray__-tagged dict. Both halves
  must reassemble back to the original arrays-first shape."""
  ps = _state(n=3, tick=7)
  ct, body = serialize_for_wire(ps)
  back = deserialize_from_wire(ct, body)
  assert isinstance(back, ParticleState)
  _assert_state_equal(back, ps)


def test_dict_containing_particle_state_round_trips():
  payload = {"meta": "hi", "frame": _state(n=1, ink=2, tick=42, w=400, h=300)}
  ct, body = serialize_for_wire(payload)
  back = deserialize_from_wire(ct, body)
  assert back["meta"] == "hi"
  assert isinstance(back["frame"], ParticleState)
  # Field-level checks: the ink rows are at indices 1, 2 in the test state
  assert back["frame"].types[0] == "water"
  assert back["frame"].types[1] == "ink"
  assert back["frame"].masses[1] == "medium"
  _assert_state_equal(back["frame"], payload["frame"])


def test_plain_json_values_pass_through_unchanged():
  # Numbers, strings, lists, dicts, None — nothing dataclass-y.
  for v in [42, "hello", [1, 2, 3], {"a": 1, "b": [True, False]}, None]:
    ct, body = serialize_for_wire(v)
    assert ct == "json"
    assert deserialize_from_wire(ct, body) == v


def test_existing_plain_json_snapshots_still_load():
  """Snapshots captured before the codec landed are plain JSON (no
  __dataclass__ tag). They must keep deserializing as dicts/lists so
  upgrade doesn't invalidate the snapshot store on disk."""
  back = deserialize_from_wire("json", '{"x": 1, "y": [2, 3]}')
  assert back == {"x": 1, "y": [2, 3]}


def test_unresolvable_dataclass_qname_raises():
  """Sanity: a tampered or stale snapshot referencing a class that no
  longer exists should fail loud rather than silently dropping fields."""
  import pytest
  body = '{"__dataclass__": "no.such.module.Class", "fields": {"x": 1}}'
  with pytest.raises(ValueError, match="cannot resolve dataclass"):
    deserialize_from_wire("json", body)


# ---------------------------------------------------------------------------
# numpy.ndarray codec round-trip (`__ndarray__`-tagged JSON)
#
# Added so edges returning raw arrays (Phase 5's detect_particle_collisions
# returns a (M, 2) pairs array; the pending ParticleState refactor makes
# every per-particle field an ndarray) can be snapshotted without the
# "ndarray not wire-serializable" warning that previously skipped capture.
# ---------------------------------------------------------------------------

import numpy as np


def _roundtrip(value):
  ct, body = serialize_for_wire(value)
  assert ct == "json"
  # Going through the JSON text channel — not just dict roundtrip — so
  # we cover what snapshot files on disk look like.
  return deserialize_from_wire(ct, body)


def test_ndarray_1d_float_round_trips():
  arr = np.array([1.5, -2.25, 3.75, 0.0], dtype=np.float64)
  back = _roundtrip(arr)
  assert isinstance(back, np.ndarray)
  assert back.dtype == arr.dtype
  assert back.shape == arr.shape
  assert np.array_equal(back, arr)


def test_ndarray_1d_int_round_trips():
  arr = np.array([0, 1, 2, 3, 4], dtype=np.int64)
  back = _roundtrip(arr)
  assert isinstance(back, np.ndarray)
  assert back.dtype == arr.dtype
  assert back.shape == arr.shape
  assert np.array_equal(back, arr)


def test_ndarray_2d_collision_pairs_round_trip():
  # The actual shape Phase 5's detect_particle_collisions emits: (N, 2)
  # int array of (i, j) pairs.
  pairs = np.array([[0, 5], [1, 7], [3, 9], [12, 14]], dtype=np.int64)
  back = _roundtrip(pairs)
  assert isinstance(back, np.ndarray)
  assert back.dtype == pairs.dtype
  assert back.shape == (4, 2)
  assert np.array_equal(back, pairs)


def test_ndarray_empty_round_trips():
  # detect_particle_collisions can legitimately return zero pairs in a
  # tick where nothing is colliding. The (0, 2) shape must survive.
  empty = np.empty((0, 2), dtype=np.int64)
  back = _roundtrip(empty)
  assert isinstance(back, np.ndarray)
  assert back.dtype == empty.dtype
  assert back.shape == (0, 2)
  assert np.array_equal(back, empty)


def test_ndarray_object_dtype_strings_round_trips():
  # Mimics what ParticleState.types becomes after the planned refactor:
  # an object-dtype array of short string literals.
  types = np.array(["water", "ink", "water", "water"], dtype=object)
  back = _roundtrip(types)
  assert isinstance(back, np.ndarray)
  assert back.dtype == types.dtype
  assert back.shape == types.shape
  assert np.array_equal(back, types)
  assert all(isinstance(x, str) for x in back.tolist())


def test_ndarray_inside_dict_round_trips():
  # Composition: arrays nested in containers (the shape every realistic
  # snippet returns) must still recurse through the encoder.
  payload = {"pairs": np.array([[1, 2], [3, 4]], dtype=np.int32),
             "label": "tick-42"}
  back = _roundtrip(payload)
  assert back["label"] == "tick-42"
  assert isinstance(back["pairs"], np.ndarray)
  assert np.array_equal(back["pairs"], payload["pairs"])
  assert back["pairs"].dtype == payload["pairs"].dtype


# ----------------------------------------------------------------------
# unify-compute-serialization (engine debt cleanup):
# serialize_result now wire-encodes ParticleState as moda_sim_state for
# the HTTP-response path, and falls through to _dataclass_to_jsonable
# for any other dataclass+ndarray return. serialize_for_wire continues
# to round-trip losslessly via the dataclass codec (its contract is
# read-back, not render — moda_sim_state's row-oriented shape is lossy
# w.r.t. internal arrays like headings/speeds/width/height).
# ----------------------------------------------------------------------

def test_serialize_result_emits_moda_sim_state_for_particle_state():
  ps = _state(n=3, ink=2, tick=42, w=400, h=300)
  out = serialize_result(ps)
  assert isinstance(out, dict)
  assert out["type"] == "moda_sim_state"
  content = out["content"]
  assert content["tick"] == 42
  particles = content["particles"]
  # 3 water + 2 ink rows materialized row-oriented for the iframe.
  assert len(particles) == 5
  # Row-shape keys match the iframe's Particle interface.
  assert set(particles[0].keys()) == {"id", "type", "x", "y", "mass"}
  # First three rows are water, last two are ink (per _state setup).
  assert [p["type"] for p in particles] == ["water"] * 3 + ["ink"] * 2


def test_serialize_result_idempotent_on_tagged_input():
  """Re-feeding an already-tagged native-wire-format dict returns the
  same shape, not a re-wrapped one. Guards the idempotency early-
  return."""
  tagged = {"type": "moda_sim_state",
            "content": {"tick": 0, "particles": []}}
  assert serialize_result(tagged) is tagged

  musicxml = {"type": "musicxml", "content": "<score-partwise>...</score-partwise>"}
  assert serialize_result(musicxml) is musicxml


def test_serialize_result_falls_through_to_dataclass_codec_for_other_dataclasses():
  """A dataclass NOT recognized by music21 or particle_state recognizers
  still wire-encodes via _dataclass_to_jsonable rather than passing
  through raw. This is the closing of the asymmetry with
  serialize_for_wire."""
  p = Particle(id=1, type="water", x=10.5, y=20.5,
               heading=1.5, speed=50.0, mass="medium")
  out = serialize_result(p)
  # Tagged dataclass form (the codec's standard shape).
  assert isinstance(out, dict)
  assert "__dataclass__" in out
  assert out["__dataclass__"].endswith(".Particle")
  assert out["fields"]["id"] == 1
  assert out["fields"]["type"] == "water"


def test_serialize_for_wire_still_round_trips_particle_state_losslessly():
  """Snapshot path must NOT emit moda_sim_state shape (which is lossy
  — drops headings/speeds/width/height). It uses the dataclass codec
  on the original value so deserialize_from_wire reconstructs the
  full ParticleState."""
  ps = _state(n=3, tick=7)
  ct, body = serialize_for_wire(ps)
  assert ct == "json"  # NOT "moda_sim_state"
  back = deserialize_from_wire(ct, body)
  assert isinstance(back, ParticleState)
  _assert_state_equal(back, ps)
