# Wire format — supported types

Forge's wire-format codec is the machinery that converts Python values
returned from `compute` into JSON-friendly structures (or text) suitable
for two destinations:

- HTTP responses from the backend to the plugin.
- Snapshot bodies stored as markdown text under `<vault>/.forge/edges/`.

The codec is one half of the snapshot/freeze story: a value can be
snapshotted (and therefore frozen) only if the codec knows how to
encode it. Constitution F3 establishes the principle; this document
enumerates the current contents.

## Principle

The codec is a pair of dispatchers — an encoder and a decoder — that
inspect the Python value's type and route it through a per-type
codec. The base set ships with Forge core. Domain layers may register
additional encodings (e.g., `music21.stream.Stream` for music; future
domain types as they emerge).

If a value reaches the dispatcher and no codec matches, capture is
skipped, a warning is logged, and compute continues. The edge cannot
be frozen until a codec is added.

## Supported types

### Primitives

| Python type | Encoded as | Notes |
|-------------|-----------|-------|
| `int`, `float`, `bool`, `None` | JSON primitive | Lossless round-trip. |
| `str` | JSON string | Lossless round-trip. |

### Containers

| Python type | Encoded as | Notes |
|-------------|-----------|-------|
| `list`, `tuple` | JSON array (recursively encoded) | Tuples decode back as lists by default. |
| `dict` | JSON object (recursively encoded) | Keys must be strings (JSON limitation). |

### Dataclasses

| Python type | Encoded as | Notes |
|-------------|-----------|-------|
| `@dataclass` instance | `{"__class__": "<qualname>", "fields": {...}}` | Fields recursively encoded. Decoder looks up the class by qualname in a registry seeded by domain modules. |

Used for `Particle`, `ParticleState` (moda domain), and any other
domain dataclasses registered through `forge/<domain>/types.py`.

### Domain types

| Python type | Domain | Encoded as | Notes |
|-------------|--------|-----------|-------|
| `music21.stream.Stream` (and subclasses) | music | MusicXML string | Rendered inline by the plugin's Verovio renderer. |

### Binary content

| Python type | Encoded as | Notes |
|-------------|-----------|-------|
| `(bytes, content_type)` tuple | `{"__binary__": true, "bytes_b64": "...", "content_type": "..."}` | Used exclusively for binary data snippets (image/audio/video). Caller side unpacks the tuple. |

## Not yet supported

- `numpy.ndarray` — planned, in progress. Will encode as
  `{"__ndarray__": true, "dtype": "...", "shape": [...], "data": [...]}`
  with `data` derived from `arr.tolist()`. Required for the
  `ParticleState` refactor (see `tech-debt.md`).
- `set`, `frozenset` — no current consumer. If needed, encode as
  ordered JSON array with a tag.
- Pandas `DataFrame`, `Series` — no current consumer. Likely a
  future need for forge-data or analysis-domain vaults.

## Extension pattern

To add a new type:

1. Implement encode and decode functions in
   `forge/core/serialization.py` (or a domain module under
   `forge/<domain>/`) following the existing dispatch shape.
2. Register them with the codec dispatcher at module load time, the
   same way `forge.music.llm_prompt` registers its prompt fragment.
3. Add round-trip tests (encode → decode produces a value equal to
   the input).
4. Add an entry to the relevant table in this document.
5. If the new type is domain-scoped, mention it in the domain's
   prompt fragment so the LLM knows it's a valid return type.

## Versioning

The wire format itself is unversioned; each per-type encoder writes
its own tag (e.g., `__class__`, `__ndarray__`) so a decoder can
dispatch unambiguously. Breaking changes to an existing type's
encoding would require either a new tag or a migration of existing
snapshot files — neither has been needed yet.
