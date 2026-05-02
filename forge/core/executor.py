import io
import re
import sys
import math
import random
import numpy
import builtins

# Domain modules pre-injected into the snippet namespace. Untrusted snippets
# can't `import`, so anything they should be able to call has to be here.
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
  }
except ImportError:
  _MUSIC21_NAMES = {}

_PYTHON_HEADING = re.compile(r'^#{1,6}\s+python\s*$', re.IGNORECASE)

_SAFE_BUILTINS = {name: getattr(builtins, name) for name in (
  "print", "len", "range", "enumerate", "zip", "map", "filter",
  "sorted", "reversed", "list", "dict", "set", "tuple", "str",
  "int", "float", "bool", "type", "isinstance", "hasattr", "getattr",
  "min", "max", "sum", "abs", "round", "any", "all", "repr", "format",
  "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
) if hasattr(builtins, name)}


class SnippetExecError(Exception):
  def __init__(self, message, stdout=""):
    super().__init__(message)
    self.stdout = stdout


class ForgeContext:
  """Passed as the `context` argument to run(context). Carries session state and
  allows snippets to call other snippets."""

  def __init__(self, resolver, inputs, vault_path=None, registry=None, caller_id=None):
    self._resolver = resolver
    self._inputs = inputs
    self.vault_path = vault_path
    self.registry = registry
    # The currently-executing snippet's qualified ID. Used as the `caller` for
    # any edges captured by context.compute calls from this scope. None at the
    # top level (no enclosing snippet — no edges to capture).
    self._caller_id = caller_id

  def get(self, key, default=None):
    return self._inputs.get(key, default)

  def __getitem__(self, key):
    return self._inputs[key]

  def compute(self, snippet_id, *args, **inputs):
    if self._resolver is None:
      raise RuntimeError("context.compute requires a resolver")
    # SnippetResolutionError propagates with structured "searched" info per ADR 0002
    snippet = self._resolver.resolve(snippet_id)
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
      )
      if nested_stdout:
        sys.stdout.write(nested_stdout)
    elif snippet_type in ("data", "snapshot"):
      result = read_data_snippet(snippet)
    else:
      raise ValueError(f"unknown type '{snippet_type}' for snippet '{snippet_id}'")

    self._capture_edge(snippet, result)
    return result

  def _capture_edge(self, callee_snippet, value):
    """Write a snapshot for the (caller, callee) edge per A7. Skipped when:
    - There's no enclosing snippet (top-level /compute — no edge exists).
    - vault_path isn't set (raw exec_python in a test, no filesystem to write to).
    - The value isn't wire-serializable (Manifest objects, file handles, etc.
      that pass between sub-snippets in pipelines like install). A divergence
      from a strict read of A7: capture is best-effort; values that can't be
      round-tripped through the wire format are logged and skipped rather
      than crashing the compute.
    """
    if self._caller_id is None or self.vault_path is None:
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
      import logging
      logging.getLogger(__name__).debug(
        "snapshot capture skipped for %s -> %s: %s",
        self._caller_id, callee_snippet["snippet_id"], e,
      )


def read_data_snippet(snippet):
  """Deserialize a data/snapshot snippet's body via its content_type (D3, F3)."""
  from forge.core.serialization import deserialize_from_wire
  meta = snippet["meta"]
  content_type = meta.get("content_type")
  if not content_type:
    raise ValueError(f"data snippet '{snippet['snippet_id']}' has no content_type in frontmatter")
  body = _strip_code_fence(snippet["body"])
  return deserialize_from_wire(content_type, body)


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


def exec_python(code, inputs, resolver=None, args=(), vault_path=None, registry=None, trusted=False, snippet_id=None):
  buf = io.StringIO()
  context = ForgeContext(resolver, inputs, vault_path=vault_path, registry=registry, caller_id=snippet_id)
  builtins_for_exec = builtins.__dict__ if trusted else _SAFE_BUILTINS
  local_ns = {
    **inputs,
    "inputs": inputs,
    "__builtins__": builtins_for_exec,
    "random": random,
    "math": math,
    "numpy": numpy,
    **_MUSIC21_NAMES,
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
    has_var_pos = any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())
    has_var_kw = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
    return len(pos_params) == 1 and not has_var_pos and not has_var_kw
  except (ValueError, TypeError):
    return False
