"""V2-shape detection — does this snippet body use the V2 dialect?

Strategy per spike prompt §3.1 Pick A: auto-detect by presence of `# Recipe`
heading. V1 notes (with `# English` + `# Python` facets) go through the
legacy path. V2 notes get the new parser + transpiler.

Frontmatter is stripped before checking so a note with body content
including `# Recipe` strictly in frontmatter doesn't false-positive.

v2-spec §4.7 — `## Inputs` subsection inside `# Description` declares
the compute() kwargs. `extract_inputs_declarations` parses these so
the transpiler can emit `def compute(context, name=default, ...)`.
"""

import ast as _py_ast
import re
from dataclasses import dataclass
from typing import List, Optional


_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_RECIPE_HEADING_RE = re.compile(r"^#\s+Recipe\s*$", re.MULTILINE)
_DESCRIPTION_HEADING_RE = re.compile(r"^#\s+Description\s*$", re.MULTILINE)
_INPUTS_HEADING_RE = re.compile(r"^##\s+Inputs\s*$", re.MULTILINE)
# `- name (default value) — description`. The em-dash can also appear as
# a plain `--` (some keyboards). Default is optional.
_INPUT_LINE_RE = re.compile(
  r"^-\s+([A-Za-z_]\w*)(?:\s*\(\s*default\s+(.+?)\s*\))?"
  r"\s*(?:[—–-]{1,2}\s*(.*))?$"
)


@dataclass
class InputDecl:
  name: str
  default: object   # parsed Python literal, or None if no default
  has_default: bool
  doc: str


def detect_recipe_shape(snippet_body: str) -> bool:
  """True iff the snippet body has a `# Recipe` heading (after frontmatter)."""
  body = _strip_frontmatter(snippet_body)
  return bool(_RECIPE_HEADING_RE.search(body))


def extract_recipe_body(snippet_body: str) -> str:
  """Pull the lines after `# Recipe` and before the next `#`-level heading
  (or end of body). Raises ValueError if no `# Recipe` heading is present.

  Preserves indentation so the parser can use indent-based block
  structure for Repeat / For each / If.
  """
  body = _strip_frontmatter(snippet_body)
  match = _RECIPE_HEADING_RE.search(body)
  if not match:
    raise ValueError("No `# Recipe` heading found in snippet body")
  start = match.end()
  # Find next heading at the same level (`# ...`) — strict prefix match so
  # `## Inputs` (a Description subsection) wouldn't trigger.
  rest = body[start:]
  next_heading = re.search(r"^# [^\n]*$", rest, re.MULTILINE)
  if next_heading:
    return rest[: next_heading.start()].strip("\n")
  return rest.strip("\n")


def _strip_frontmatter(body: str) -> str:
  return _FRONTMATTER_RE.sub("", body, count=1)


def extract_inputs_declarations(snippet_body: str) -> List[InputDecl]:
  """Parse `## Inputs` subsection (inside `# Description`) into a list
  of InputDecl records.

  Format per v2-spec §4.7: `- name (default value) — description`.
  - `(default ...)` parenthetical is optional. Value parsed via
    ast.literal_eval (int / float / string / list / bool / None).
  - `— description` is optional. Em-dash, en-dash, or `--` accepted.
  - Lines that don't match the input shape are ignored (e.g.,
    `(none)` placeholder, prose).

  Returns:
    Ordered list of InputDecl. Empty when no `## Inputs` heading or
    no recognizable declarations.
  """
  body = _strip_frontmatter(snippet_body)
  inputs_match = _INPUTS_HEADING_RE.search(body)
  if not inputs_match:
    return []
  start = inputs_match.end()
  # Stop at next `##`- or `#`-level heading.
  next_heading = re.search(r"^#{1,2} [^\n]*$", body[start:], re.MULTILINE)
  region = body[start:start + next_heading.start()] if next_heading else body[start:]
  out: List[InputDecl] = []
  for line in region.splitlines():
    m = _INPUT_LINE_RE.match(line.rstrip())
    if not m:
      continue
    name, default_str, doc = m.groups()
    has_default = default_str is not None
    if has_default:
      try:
        default = _py_ast.literal_eval(default_str.strip())
      except (ValueError, SyntaxError):
        # Treat unparsable as string literal.
        default = default_str.strip()
    else:
      default = None
    out.append(InputDecl(
      name=name,
      default=default,
      has_default=has_default,
      doc=(doc or "").strip(),
    ))
  return out
