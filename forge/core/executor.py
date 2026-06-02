import io
import re
import sys
import math
import random
import numpy
import builtins

# Domain modules pre-injected into the snippet namespace for convenience —
# snippets can use them without importing. Snippets get full Python power
# (including `import` and the full builtins), per constitution B2; this
# pre-injection is ergonomics, not sandboxing.
try:
  import music21
  _MUSIC21_NAMES = {
    "music21": music21,
    "stream": music21.stream,
    "note": music21.note,
    "chord": music21.chord,
    "meter": music21.meter,
    "key": music21.key,
    "tempo": music21.tempo,
    "pitch": music21.pitch,
    "duration": music21.duration,
    "instrument": music21.instrument,
    "harmony": music21.harmony,
    "roman": music21.roman,
  }
except ImportError:
  _MUSIC21_NAMES = {}

try:
  from forge.music import lib as _music_lib
  _FORGE_MUSIC_LIB_NAMES = {
    "bar": _music_lib.bar,
    "voices": _music_lib.voices,
    "sequence": _music_lib.sequence,
    "repeat": _music_lib.repeat,
    "minor_pentatonic": _music_lib.minor_pentatonic,
    "major_pentatonic": _music_lib.major_pentatonic,
    "with_velocity": _music_lib.with_velocity,
  }
except ImportError:
  _FORGE_MUSIC_LIB_NAMES = {}

try:
  from forge.moda.types import Particle as _ModaParticle, ParticleState as _ModaParticleState
  _FORGE_MODA_NAMES = {
    "Particle": _ModaParticle,
    "ParticleState": _ModaParticleState,
  }
except ImportError:
  _FORGE_MODA_NAMES = {}

# Domain-scoped global injection (constitution B9 / domain-scoping).
# Each domain's pre-injected names register under its domain key,
# mirroring the prompt-fragment registry. The base names (random,
# math, numpy) are always injected regardless of declared domains;
# only these domain bundles are gated.
_DOMAIN_GLOBALS = {
  "music": {**_MUSIC21_NAMES, **_FORGE_MUSIC_LIB_NAMES},
  "moda": _FORGE_MODA_NAMES,
}


def _domain_globals_for(domains):
  """Return the merged domain-global dict for the active domains.

  domains is None  -> all registered domains (back-compat: vault did
                       not declare `domains` in forge.toml).
  domains is []    -> {} (core-only: just the base names).
  domains is [...] -> only those domains' bundles.
  """
  if domains is None:
    selected = _DOMAIN_GLOBALS.values()
  else:
    allow = set(domains)
    selected = (v for k, v in _DOMAIN_GLOBALS.items() if k in allow)
  merged = {}
  for bundle in selected:
    merged.update(bundle)
  return merged

_PYTHON_HEADING = re.compile(r'^#{1,6}\s+python\s*$', re.IGNORECASE)

_NO_FROZEN_SNAPSHOT = object()


class SnippetExecError(Exception):
  def __init__(self, message, stdout=""):
    super().__init__(message)
    self.stdout = stdout


class SnapshotCaptureError(Exception):
  """Raised when an action snippet returns a value the wire-format codec
  can't serialize AND the snippet hasn't opted out of capture via
  `snapshot_capture: false` in frontmatter.

  Per constitution C7/A7: returns must be wire-serializable, or the
  snippet must declare it isn't capturable. Silent skips hide missing
  edges in the freeze graph and the Edges panel."""
  pass


class ForgeContext:
  """Passed as the `context` argument to run(context). Carries session state and
  allows snippets to call other snippets."""

  def __init__(self, resolver, inputs, vault_path=None, registry=None,
               caller_id=None, domains=None):
    self._resolver = resolver
    self._inputs = inputs
    self.vault_path = vault_path
    self.registry = registry
    # The currently-executing snippet's qualified ID. Used as the `caller` for
    # any edges captured by context.compute calls from this scope. None at the
    # top level (no enclosing snippet — no edges to capture).
    self._caller_id = caller_id
    # Active domain scope (constitution B9). The request's vault domains
    # govern the whole execution, including nested context.compute calls
    # (v1 permissive: cross-vault calls are not blocked at resolve time;
    # per-callee-vault re-scoping is a documented follow-up). None = all
    # domains (back-compat), [] = core-only, [...] = those domains.
    self._domains = domains

  def get(self, key, default=None):
    return self._inputs.get(key, default)

  def __getitem__(self, key):
    return self._inputs[key]

  def compute(self, snippet_id, *args, **inputs):
    if self._resolver is None:
      raise RuntimeError("context.compute requires a resolver")
    # SnippetResolutionError propagates with structured "searched" info per ADR 0002.
    # v0.2.26: thread caller_id so bare references inside library
    # subdirs (e.g. `context.compute("chorus")` from
    # `forge-music/blues/song`) probe the caller's own directory first.
    snippet = self._resolver.resolve(snippet_id, caller_id=self._caller_id)

    # A8/A9: frozen edges short-circuit. Returning the snapshot value here
    # means the callee is never invoked and its own dependencies (if any)
    # are not traversed — that's transitive freeze (F8) for free.
    frozen_value = self._read_frozen_snapshot(snippet)
    if frozen_value is not _NO_FROZEN_SNAPSHOT:
      return frozen_value

    snippet_type = snippet["meta"].get("type")

    if snippet_type == "action":
      code = extract_python(snippet["body"])
      if code is None:
        raise ValueError(f"no Python heading in snippet '{snippet_id}'")
      nested_trusted = snippet.get("source") == "builtin"
      nested_stdout, result = exec_python(
        code, inputs, self._resolver,
        args=args,
        vault_path=self.vault_path,
        registry=self.registry,
        trusted=nested_trusted,
        snippet_id=snippet["snippet_id"],
        domains=self._domains,
      )
      if nested_stdout:
        sys.stdout.write(nested_stdout)
    elif snippet_type in ("data", "snapshot"):
      result = read_data_snippet(snippet)
    else:
      raise ValueError(
        f"unknown type '{snippet_type}' for snippet '{snippet_id}'")

    self._capture_edge(snippet, result)
    return result

  def _read_frozen_snapshot(self, callee_snippet):
    """If this edge is frozen, return its deserialized snapshot value.
    Otherwise return _NO_FROZEN_SNAPSHOT (a sentinel — None is a valid
    captured value)."""
    if self._caller_id is None or self.vault_path is None:
      return _NO_FROZEN_SNAPSHOT
    from forge.core.snapshots import read_snapshot
    snap = read_snapshot(self.vault_path, self._caller_id,
                         callee_snippet["snippet_id"])
    if snap is None or snap["meta"].get("state") != "frozen":
      return _NO_FROZEN_SNAPSHOT
    from forge.core.serialization import deserialize_from_wire
    content_type = snap["meta"].get("content_type")
    if not content_type:
      return _NO_FROZEN_SNAPSHOT
    body = _strip_code_fence(snap["body"])
    return deserialize_from_wire(content_type, body)

  def read_snapshot(self):
    """Read the most recent snapshot THIS snippet produced. Returns the
    deserialized value, or None if there is none.

    Self-only — no callee_id argument (deferred per forge-core until a
    non-moda use case justifies it).

    Semantics (constitution C8 + the option-(A) limitation). Forge
    captures snapshots per *edge* (caller -> callee), keyed by the
    callee. Entry-point snippets such as moda `go` are never a callee
    — nothing calls `context.compute("go")` — so a "snapshot of go as
    seen by a caller" is never written. What IS persisted is go's own
    *outbound* edge directory `.forge/edges/<self_id>/`, holding one
    snapshot per snippet `go` called. This returns the latest of
    those. For a pass-through snippet whose return value equals its
    terminal callee's return (moda `go`), that is exactly "go's last
    output". For a snippet that post-processes state before returning,
    it would be the last sub-call's output and would lag the true
    return by that post-processing — a known, bounded limitation the
    snippet's English facet MUST declare (C8).

    Independent of freeze (F1-F9): reads the stored snapshot whatever
    the edge state.

    `captured_at` has 1-second resolution, so several snapshots written
    inside one invocation tie. Ties break by file mtime (last write
    wins) so the terminal callee — written last in the pipeline,
    i.e. the pass-through snippet's return — is the one returned.
    """
    if self._caller_id is None or self.vault_path is None:
      return None
    import os
    from forge.core.snippet_registry import parse_frontmatter
    from forge.core.serialization import deserialize_from_wire

    root = os.path.join(self.vault_path, ".forge", "edges", self._caller_id)
    if not os.path.isdir(root):
      return None

    # Collect every parseable snapshot under this snippet's outbound
    # directory, then deserialize from newest down until one succeeds.
    # Malformed files are skipped per the best-effort snapshot contract.
    candidates = []  # (captured_at, mtime, content_type, body)
    for dirpath, _dirs, files in os.walk(root):
      for fn in files:
        if not fn.endswith(".md"):
          continue
        path = os.path.join(dirpath, fn)
        try:
          with open(path, "r", encoding="utf-8") as f:
            content = f.read()
          meta, body = parse_frontmatter(content)
          if meta.get("type") != "snapshot":
            continue
          content_type = meta.get("content_type")
          if not content_type:
            continue
          candidates.append((
            meta.get("captured_at") or "",
            os.path.getmtime(path),
            content_type,
            body,
          ))
        except Exception:
          continue  # unreadable / malformed frontmatter — skip

    candidates.sort(key=lambda c: (c[0], c[1]))
    for _captured_at, _mtime, content_type, body in reversed(candidates):
      try:
        return deserialize_from_wire(content_type, _strip_code_fence(body))
      except Exception:
        continue  # malformed body — fall through to the next-newest
    return None

  def _capture_edge(self, callee_snippet, value):
    """Write a snapshot for the (caller, callee) edge per A7. Skipped when:
    - There's no enclosing snippet (top-level /compute — no edge exists).
    - vault_path isn't set (raw exec_python in a test, no filesystem to write to).
    - The callee declares `snapshot_capture: false` in frontmatter (C7
      opt-out): the author has acknowledged the return isn't capturable.

    Non-serializable returns on capture-eligible snippets RAISE
    SnapshotCaptureError (per the C7/A7 tightening: silent skips hide
    missing edges in the freeze graph and the Edges panel). The error
    names the snippet and the offending Python type so authors can
    either fix the return or declare the opt-out.
    """
    if self._caller_id is None or self.vault_path is None:
      return
    # C7 opt-out: `snapshot_capture: false` in callee frontmatter
    # skips capture silently. Default (absent) is True. We don't
    # warn on opt-out — the author has explicitly signaled intent.
    meta = callee_snippet.get("meta") or {}
    if meta.get("snapshot_capture") is False:
      return
    from forge.core.snapshots import write_snapshot
    try:
      write_snapshot(
        self.vault_path,
        self._caller_id,
        callee_snippet["snippet_id"],
        value,
        callee_snippet,
      )
    except (TypeError, ValueError) as e:
      raise SnapshotCaptureError(
        f"Cannot capture snapshot for edge "
        f"{self._caller_id}→{callee_snippet['snippet_id']}: "
        f"return value of type {type(value).__name__} is not "
        f"wire-serializable ({e}). Either return a serializable "
        f"value, or declare `snapshot_capture: false` in "
        f"frontmatter to opt out of capture for this snippet."
      ) from e


def read_data_snippet(snippet):
  """Deserialize a data/snapshot snippet's body via its content_type.

  Two paths:
  - Text content_types (json, yaml, text, markdown, svg, musicxml): payload
    is in the snippet body; returns the native python value.
  - Binary content_types (image/jpeg, image/png, audio/mpeg, audio/wav,
    video/mp4): payload lives in a sibling asset file referenced by
    `content_ref` in frontmatter; returns (bytes, content_type) tuple.

  `content_ref` and body content are mutually exclusive: a binary snippet
  must have an empty body, a text snippet must not have content_ref."""
  from forge.core.serialization import (
    deserialize_text, deserialize_binary,
    is_binary_content_type, is_text_content_type,
  )
  meta = snippet["meta"]
  snippet_id = snippet["snippet_id"]
  content_type = meta.get("content_type")
  if not content_type:
    raise ValueError(
      f"data snippet '{snippet_id}' has no content_type in frontmatter")

  content_ref = meta.get("content_ref")
  body_text = (snippet.get("body") or "").strip()

  if content_ref:
    if not is_binary_content_type(content_type):
      raise ValueError(
        f"data snippet '{snippet_id}': content_ref is only valid for binary "
        f"content_types, got content_type={content_type!r}")
    if body_text:
      raise ValueError(
        f"data snippet '{snippet_id}': content_ref and body content are "
        f"mutually exclusive, but both are present")
    asset_path = _resolve_content_ref(snippet, content_ref)
    with open(asset_path, "rb") as f:
      content_bytes = f.read()
    return deserialize_binary(content_type, content_bytes)

  if is_binary_content_type(content_type):
    raise ValueError(
      f"data snippet '{snippet_id}': binary content_type {content_type!r} "
      f"requires `content_ref` in frontmatter pointing to a sibling asset")

  if not is_text_content_type(content_type):
    raise ValueError(f"unsupported content_type: {content_type!r}")

  body = extract_body(snippet["body"])
  return deserialize_text(content_type, body)


def _resolve_content_ref(snippet, content_ref):
  """Resolve content_ref relative to the snippet's vault root. Falls back to
  resolving relative to the snippet's .md file's directory if vault_path
  isn't recorded — handy for tests that construct snippets by hand."""
  import os
  if os.path.isabs(content_ref):
    full = content_ref
  else:
    base = snippet.get("vault_path")
    if not base:
      file_path = snippet.get("path") or ""
      base = os.path.dirname(file_path) if file_path else ""
    full = os.path.join(base, content_ref) if base else content_ref
  if not os.path.isfile(full):
    raise FileNotFoundError(
      f"data snippet '{snippet['snippet_id']}': content_ref points to "
      f"missing file: {full}")
  return full


_BODY_HEADING = re.compile(r'^#{1,6}\s+body\s*$', re.IGNORECASE)


def extract_body(body):
  """Extract the data payload from a snippet body. If a `# Body` heading is
  present, take everything after it (analogous to extract_python under
  `# Python`); otherwise, treat the whole body as the payload. A surrounding
  ```<lang> ... ``` fence is stripped in either case.

  The `# Body` shape is what the plugin's "New Snippet" modal generates:
    # English
    <intent>
    # Body
    ```json
    {...}
    ```
  Plain-body data snippets (no headings, fenced or unfenced payload) remain
  supported for back-compat with snapshots and pre-template authoring.
  """
  lines = body.splitlines()
  for i, line in enumerate(lines):
    if _BODY_HEADING.match(line.strip()):
      payload = "\n".join(lines[i + 1:])
      return _strip_code_fence(payload.strip())
  return _strip_code_fence(body)


def _strip_code_fence(body):
  """A data snippet's body may be wrapped in a ```<lang> ... ``` fence for
  readability; strip it so deserializers see the raw payload."""
  text = body.strip()
  if not text.startswith("```"):
    return text
  lines = text.splitlines()
  # drop the opening fence (and any language tag)
  start = 1
  # drop the closing fence
  end = len(lines)
  if end > start and lines[-1].strip() == "```":
    end -= 1
  return "\n".join(lines[start:end])


def extract_section(body, heading):
  """Extract plain-text content under a markdown heading (any level, case-insensitive)."""
  pattern = re.compile(rf'^#{{1,6}}\s+{re.escape(heading)}\s*$', re.IGNORECASE)
  lines = body.splitlines()
  collecting = False
  section_lines = []
  for line in lines:
    if pattern.match(line.strip()):
      collecting = True
      continue
    if not collecting:
      continue
    if line.startswith("#") or line.strip() == "---":
      break
    section_lines.append(line)
  return "\n".join(section_lines).strip() or None


def extract_python(body):
  lines = body.splitlines()
  collecting = False
  in_fence = False
  code_lines = []
  for line in lines:
    if _PYTHON_HEADING.match(line.strip()):
      collecting = True
      continue
    if not collecting:
      continue
    if line.startswith("#"):
      break
    if line.strip().startswith("```python"):
      in_fence = True
      continue
    if line.strip() == "```":
      if in_fence:
        break
      continue
    code_lines.append(line)
  return "\n".join(code_lines).strip() or None


def exec_python(code, inputs, resolver=None, args=(), vault_path=None, registry=None, trusted=False, snippet_id=None, domains=None):
  buf = io.StringIO()
  context = ForgeContext(resolver, inputs, vault_path=vault_path,
                         registry=registry, caller_id=snippet_id,
                         domains=domains)
  # Per constitution B2, snippets get full Python power. The `trusted`
  # parameter is preserved for future use (e.g., distinguishing builtin from
  # vault snippets in some other capacity) but no longer controls builtins
  # exposure.
  del trusted
  # Base names are always injected; domain bundles (music21/helpers,
  # moda types) are gated by the vault's declared `domains` (B9).
  local_ns = {
    **inputs,
    "inputs": inputs,
    "__builtins__": builtins.__dict__,
    "random": random,
    "math": math,
    "numpy": numpy,
    **_domain_globals_for(domains),
  }
  old_stdout = sys.stdout
  sys.stdout = buf
  try:
    exec(compile(code, "<snippet>", "exec"), local_ns)
    fn = _find_entrypoint(local_ns, snippet_id, buf.getvalue())
    # Snippets are called as fn(context, *args, **inputs); Python's normal
    # parameter resolution maps positionals to declared params and rejects
    # mismatches with TypeError.
    if _takes_only_context(fn):
      result = fn(context)
    else:
      result = fn(context, *args, **inputs)
    local_ns["result"] = result
  except SnippetExecError:
    raise
  except Exception as e:
    raise SnippetExecError(str(e), stdout=buf.getvalue()) from e
  finally:
    sys.stdout = old_stdout
  return buf.getvalue(), local_ns.get("result")


def _find_entrypoint(local_ns, snippet_id, stdout):
  """Strict: every snippet's Python facet must define `def compute(context, ...)`."""
  fn = local_ns.get("compute")
  if callable(fn):
    return fn
  label = f"snippet '{snippet_id}'" if snippet_id else "snippet"
  raise SnippetExecError(
    f"{label} has no def compute in its Python facet",
    stdout=stdout,
  )


def _takes_only_context(fn):
  """True if the function declares exactly one positional parameter and no var-args.
  Lets snippets like `def compute(context):` ignore extra inputs cleanly."""
  import inspect
  try:
    sig = inspect.signature(fn)
    pos_params = [p for p in sig.parameters.values()
                  if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)]
    has_var_pos = any(
      p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())
    has_var_kw = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
    return len(pos_params) == 1 and not has_var_pos and not has_var_kw
  except (ValueError, TypeError):
    return False
