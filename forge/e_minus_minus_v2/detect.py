"""V2-shape detection — does this snippet body use the V2 dialect?

Strategy per spike prompt §3.1 Pick A: auto-detect by presence of `# E--`
heading. V1 notes (with `# English` + `# Python` facets) go through the
legacy path. V2 notes get the new parser + transpiler.

Frontmatter is stripped before checking so a note with body content
including `# E--` strictly in frontmatter doesn't false-positive.
"""

import re

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_EMM_HEADING_RE = re.compile(r"^#\s+E--\s*$", re.MULTILINE)


def detect_v2_shape(snippet_body: str) -> bool:
  """True iff the snippet body has a `# E--` heading (after frontmatter)."""
  body = _strip_frontmatter(snippet_body)
  return bool(_EMM_HEADING_RE.search(body))


def extract_emm_body(snippet_body: str) -> str:
  """Pull the lines after `# E--` and before the next `#`-level heading
  (or end of body). Raises ValueError if no `# E--` heading is present.

  Preserves indentation so the parser can use indent-based block
  structure for Repeat / For each / If.
  """
  body = _strip_frontmatter(snippet_body)
  match = _EMM_HEADING_RE.search(body)
  if not match:
    raise ValueError("No `# E--` heading found in snippet body")
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
