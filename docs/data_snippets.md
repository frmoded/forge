# Data snippets

Data snippets are Forge's second snippet type alongside action snippets. Where
action snippets compile English → Python and execute, data snippets are inert
stored content — no English facet, no compilation step, no LLM at runtime.
Just bytes addressable by snippet ID.

## When to use them

Reach for a data snippet when:

- You have a curated constant your snippets keep reinventing — a chord
  progression, a list of pitches, a building-code dimension.
- You captured a particularly good `compute()` result and want to reference it
  later as a stable artifact (the snapshot pattern).
- You have a reference asset — image, audio recording, schema definition —
  that downstream snippets consume.
- You have configuration shared across many snippets that's easier to read as
  data than to derive from logic.

## When *not* to use them

Anything time-varying or computed-on-demand. "Current weather in Hong Kong"
isn't a data snippet — it's an action snippet that returns data. The litmus
test: *can the body be correct forever once populated?* If yes, data snippet.
If no, action snippet.

## Two content-type families

| Family | Members | Storage | `compute()` returns |
|--------|---------|---------|---------------------|
| Text | `json`, `yaml`, `text`, `markdown`, `svg`, `musicxml` | Inline in snippet body | Native Python value (dict, str, music21 Stream, etc.) |
| Binary | `image/jpeg`, `image/png`, `audio/mpeg`, `audio/wav`, `video/mp4` | `<vault>/_assets/<snippet_id>.<ext>` (sibling file), referenced by `content_ref` in frontmatter | `(bytes, content_type)` tuple |

`content_ref` and body content are mutually exclusive — a binary snippet must
have an empty body. Pairing `content_ref` with a text content type is a
config error.

## Authoring

In the New Snippet modal:

- Pick `type: data`.
- Pick a `content_type` from the dropdown.
- For text content types, paste content into the body.
- For binary content types, drag-and-drop the file into the drop zone. Forge
  copies it to `_assets/` and writes the wrapper `.md` automatically.

The resulting frontmatter for text:

```yaml
type: data
content_type: json
description: Twelve-bar blues progression in I-IV-V form.
```

For binary:

```yaml
type: data
content_type: image/jpeg
content_ref: _assets/cat_reference.jpg
description: Reference photo for the architectural sketch.
```

## Capturing from compute

After running an action snippet, the output panel shows a "Save as data
snippet" button. Click it, name the snippet, and Forge:

- Auto-detects the content_type from the result.
- For text-shaped results, writes content into the snippet body.
- For binary results, writes a sibling asset and a wrapper `.md` with
  `content_ref`.

This is the snapshot pattern: ephemeral compute results become addressable,
durable artifacts.

## Consuming

```python
def compute(context):
    # Text data snippet — returns native value
    progression = context.compute("twelve_bar_blues_progression")  # list[str]

    # musicxml data snippet — returns music21 Stream
    phrase = context.compute("weary_descending_phrase")
    return voices(form, phrase)

    # Binary data snippet — unpack the tuple
    # data, ct = context.compute("cat_reference")  # bytes, "image/jpeg"
```

The system prompt teaches the LLM the binary unpack idiom, so generated caller
code uses the right shape automatically.

## Read-only state

Data snippets can be marked read-only via frontmatter (`read_only: true`).
Useful for canonical references that downstream snippets structurally depend
on — once read-only, edits in the editor require explicit toggle-off. This is
distinct from *edge freezing* (which acts on caller→callee edges, not on
snippets themselves).

Use read-only when a data snippet acts as an interface — for example, a JSON
list whose shape downstream parsers depend on. Skip it for snippets that are
expected to evolve.

## Music vault examples

Three patterns from `forge-music-core`:

- `twelve_bar_blues_progression` — JSON list of chord symbols. Canonical
  reference; mark read-only. Action snippets read this rather than hardcoding
  `['E7', 'E7', ...]`.
- `e_minor_pentatonic_pitches` — JSON list of pitch names. Same pattern.
- `weary_descending_phrase` — musicxml data snippet captured via Save from
  compute. Frozen as a named artifact and reused inside larger compositions.

## Related

- Constitution: D1–D6 for the architectural specification.
- Snapshots: F1–F9 for system-generated read-only data snippets capturing
  compute results on DAG edges.
