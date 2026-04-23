import io
import re
import sys
import builtins

_PYTHON_HEADING = re.compile(r'^#{1,6}\s+python\s*$', re.IGNORECASE)

_SAFE_BUILTINS = {name: getattr(builtins, name) for name in (
  "print", "len", "range", "enumerate", "zip", "map", "filter",
  "sorted", "reversed", "list", "dict", "set", "tuple", "str",
  "int", "float", "bool", "type", "isinstance", "hasattr", "getattr",
  "min", "max", "sum", "abs", "round", "any", "all", "repr", "format",
  "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
) if hasattr(builtins, name)}


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


def exec_python(code, kwargs):
  buf = io.StringIO()
  local_ns = {**kwargs, "kwargs": kwargs, "__builtins__": _SAFE_BUILTINS}
  old_stdout = sys.stdout
  sys.stdout = buf
  try:
    exec(compile(code, "<snippet>", "exec"), local_ns)
    if callable(local_ns.get("run")):
      result = local_ns["run"](kwargs)
      local_ns["result"] = result
  finally:
    sys.stdout = old_stdout
  return buf.getvalue(), local_ns.get("result")
