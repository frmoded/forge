import io
import re
import sys
import math
import random
import numpy
import builtins

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

  def __init__(self, resolver, kwargs, vault_path=None, registry=None):
    self._resolver = resolver
    self._kwargs = kwargs
    self.vault_path = vault_path
    self.registry = registry

  def get(self, key, default=None):
    return self._kwargs.get(key, default)

  def __getitem__(self, key):
    return self._kwargs[key]

  def execute(self, snippet_id, **kwargs):
    if self._resolver is None:
      raise RuntimeError("context.execute requires a resolver")
    # SnippetResolutionError propagates with structured "searched" info per ADR 0002
    snippet = self._resolver.resolve(snippet_id)
    meta = snippet["meta"]
    body = snippet["body"]
    snippet_type = meta.get("type")
    if snippet_type == "action":
      code = extract_python(body)
      if code is None:
        raise ValueError(f"no Python heading in snippet '{snippet_id}'")
      nested_trusted = snippet.get("source") == "builtin"
      nested_stdout, result = exec_python(
        code, kwargs, self._resolver,
        vault_path=self.vault_path,
        registry=self.registry,
        trusted=nested_trusted,
      )
      if nested_stdout:
        sys.stdout.write(nested_stdout)
      return result
    if snippet_type == "data":
      return {k: v for k, v in meta.items() if k not in ("type", "title", "description", "inputs")}
    raise ValueError(f"unknown type '{snippet_type}' for snippet '{snippet_id}'")


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


def exec_python(code, kwargs, resolver=None, vault_path=None, registry=None, trusted=False):
  buf = io.StringIO()
  context = ForgeContext(resolver, kwargs, vault_path=vault_path, registry=registry)
  builtins_for_exec = builtins.__dict__ if trusted else _SAFE_BUILTINS
  local_ns = {**kwargs, "kwargs": kwargs, "__builtins__": builtins_for_exec, "random": random, "math": math, "numpy": numpy}
  pre_exec_keys = set(local_ns.keys())
  old_stdout = sys.stdout
  sys.stdout = buf
  try:
    exec(compile(code, "<snippet>", "exec"), local_ns)
    fn = _find_entrypoint(local_ns, pre_exec_keys)
    if fn is not None:
      result = fn(context, **kwargs) if _takes_kwargs(fn) else fn(context)
      local_ns["result"] = result
  except Exception as e:
    raise SnippetExecError(str(e), stdout=buf.getvalue()) from e
  finally:
    sys.stdout = old_stdout
  return buf.getvalue(), local_ns.get("result")


def _find_entrypoint(local_ns, pre_exec_keys):
  """Prefer run(); fall back to the first callable added by the snippet."""
  if callable(local_ns.get("run")):
    return local_ns["run"]
  new_callables = [
    v for k, v in local_ns.items()
    if k not in pre_exec_keys and callable(v) and not k.startswith("_")
  ]
  return new_callables[0] if new_callables else None


def _takes_kwargs(fn):
  """True if the function accepts more than one positional argument."""
  import inspect
  try:
    sig = inspect.signature(fn)
    params = [p for p in sig.parameters.values()
              if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)]
    return len(params) > 1
  except (ValueError, TypeError):
    return False
