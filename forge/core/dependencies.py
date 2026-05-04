"""Static dependency analysis on snippet Python facets (constitution B7).

Extracts the snippet IDs a Python facet calls via context.compute("...") and
formats / strips the Dependencies section in a snippet body.
"""

import ast
from typing import List


def extract_dependencies(python_source: str) -> List[str]:
  """Return snippet IDs the source statically calls via context.compute(...).

  Only literal string first arguments are extracted. Dynamic dispatch
  (f-strings, variables, computed names) is silently skipped — those edges
  aren't statically discoverable. Deduplicated, source order. Empty list on
  parse failure.
  """
  try:
    tree = ast.parse(python_source)
  except SyntaxError:
    return []

  found: list[tuple[int, int, str]] = []
  for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
      continue
    func = node.func
    if not isinstance(func, ast.Attribute):
      continue
    if func.attr != "compute":
      continue
    if not isinstance(func.value, ast.Name) or func.value.id != "context":
      continue
    if not node.args:
      continue
    first = node.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
      continue
    found.append((node.lineno, node.col_offset, first.value))

  found.sort()
  out: list[str] = []
  seen: set[str] = set()
  for _, _, sid in found:
    if sid not in seen:
      seen.add(sid)
      out.append(sid)
  return out


_DEPS_HEADER = "# Dependencies"
_DEPS_NOTE = (
  '*Synced from Python. Edit the Python and regenerate, or run '
  '"Forge: Sync edges" to refresh.*'
)


def apply_dependencies_to_body(body: str, deps: List[str]) -> str:
  """Insert/replace/remove the Dependencies section in a body.

  Idempotent: applying the same deps twice produces the same string. The
  section is placed at the bottom of the body. Empty deps removes the
  section if present.
  """
  stripped = _strip_dependencies_section(body)
  trimmed = stripped.rstrip() + "\n"
  if not deps:
    return trimmed
  links = " ".join(f"[[{d}]]" for d in deps)
  section = f"{_DEPS_HEADER}\n\n{_DEPS_NOTE}\n\n{links}\n"
  return trimmed + "\n" + section


def _strip_dependencies_section(body: str) -> str:
  lines = body.splitlines()
  out: list[str] = []
  i = 0
  while i < len(lines):
    if lines[i].strip() == _DEPS_HEADER:
      # skip until next top-level heading or EOF
      i += 1
      while i < len(lines) and not lines[i].lstrip().startswith("# "):
        i += 1
    else:
      out.append(lines[i])
      i += 1
  return "\n".join(out)
