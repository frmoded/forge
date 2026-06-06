"""Slot-cache helpers for canonical-form snippet `{{ ... }}` value
slots (Phase 1 design, not yet wired).

Three helpers:

- parse_slots_section(body)  →  dict[str, str]
- serialize_slots_section(slots)  →  str
- compute_slot_cache_key(slot_text, snippet_id, surrounding_context=None)
   →  str (hex sha256)

The cache shape matches the design in
docs/investigations/slot-resolution-design.md §B: a sidecar `# Slots`
heading inside the snippet's .md, containing a YAML-encoded dict of
cache_key → python_expr. Helpers are tolerant of missing / malformed
input (return {} on parse error) mirroring extract_python's shape at
executor.py:508.

NOT YET WIRED. Phase 2 will call parse_slots_section from the
canonical compile path at executor.py:486-505 and serialize_slots_section
from the plugin-side cache write path. This module is Pyodide-safe:
no I/O, no os.environ, no anthropic client.
"""

from __future__ import annotations

import hashlib
import re

import yaml


_SLOTS_HEADING = re.compile(r"^#\s+slots\s*$", re.IGNORECASE)
_NEXT_HEADING = re.compile(r"^#\s+\S")
_YAML_FENCE_OPEN = re.compile(r"^\s*```ya?ml\s*$", re.IGNORECASE)
_YAML_FENCE_CLOSE = re.compile(r"^\s*```\s*$")


def parse_slots_section(body):
  """Extract the # Slots YAML heading from a snippet body.

  Returns a dict mapping cache_key (hex string) to python_expr (str).
  Returns {} when no # Slots heading is present, when the heading
  exists but its YAML body is empty, when the YAML is malformed, or
  when the top-level shape isn't dict-of-strings.

  Tolerant by design — a malformed cache shouldn't crash the engine;
  the next transpile will re-resolve missing entries via /resolve-slot
  and the plugin will rewrite the heading cleanly.

  Mirrors extract_python's tolerance at executor.py:508.
  """
  lines = body.splitlines() if body else []
  yaml_lines = []
  state = "scanning"
  for line in lines:
    if state == "scanning":
      if _SLOTS_HEADING.match(line.strip()):
        state = "in_section"
      continue
    if state == "in_section":
      # Next top-level heading ends the section.
      if _NEXT_HEADING.match(line):
        break
      if _YAML_FENCE_OPEN.match(line):
        state = "in_fence"
        continue
      # Tolerate raw YAML without fences (less common but valid).
      yaml_lines.append(line)
    elif state == "in_fence":
      if _YAML_FENCE_CLOSE.match(line):
        state = "after_fence"
        continue
      yaml_lines.append(line)
    elif state == "after_fence":
      # After a closed fence, only blank lines or the next heading
      # are expected. Stop on any non-blank non-heading content.
      if _NEXT_HEADING.match(line):
        break
      if line.strip():
        break

  text = "\n".join(yaml_lines).strip()
  if not text:
    return {}

  try:
    data = yaml.safe_load(text)
  except yaml.YAMLError:
    return {}

  if not isinstance(data, dict):
    return {}

  # Accept either a flat dict or a `slots:` wrapper per the design.
  if "slots" in data and isinstance(data["slots"], dict):
    candidate = data["slots"]
  else:
    candidate = data

  # Filter: only str → str pairs survive. A future cache version that
  # extends the value type will widen this filter; today the contract
  # is single-line Python expressions as strings.
  out = {}
  for k, v in candidate.items():
    if isinstance(k, str) and isinstance(v, str):
      out[k] = v
  return out


def serialize_slots_section(slots):
  """Inverse of parse_slots_section: render a slots dict as the body
  of a `# Slots` heading, including the heading line itself.

  Stable ordering by cache_key (asciibetical) for diff-friendliness.
  Returns the empty string for an empty dict — callers omit the
  heading entirely when there's nothing to cache.

  Output shape:

      # Slots

      ```yaml
      slots:
        "<cache_key_1>": "<python_expr_1>"
        "<cache_key_2>": "<python_expr_2>"
      ```

  The wrapper `slots:` key is load-bearing for forward compatibility
  per the design's "self-describing top-level shape" note.
  """
  if not slots:
    return ""
  body_lines = ["# Slots", "", "```yaml", "slots:"]
  for key in sorted(slots.keys()):
    value = slots[key]
    # YAML double-quoted string escaping: escape backslashes and
    # double quotes only. Single-line Python expressions don't
    # contain raw newlines (the resolver validates single-line);
    # multi-line expressions are out of scope per E-- spec §4.4.2.
    escaped_key = key.replace("\\", "\\\\").replace('"', '\\"')
    escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
    body_lines.append(f'  "{escaped_key}": "{escaped_value}"')
  body_lines.append("```")
  return "\n".join(body_lines) + "\n"


def compute_slot_cache_key(slot_text, snippet_id,
                           surrounding_context=None):
  """Stable cache key for a (slot_text, snippet_id, context) triple.

  Returns hex-encoded sha256. Determinism is a HARD requirement —
  same inputs MUST produce the same output across Python versions and
  platforms. sha256 + UTF-8 encoding satisfies this.

  The triple is joined by a null-byte separator (`\\x00`) so distinct
  values can't collide via concatenation ambiguity (e.g., snippet_id
  "ab" + slot_text "c" must not collide with snippet_id "a" +
  slot_text "bc").

  surrounding_context=None contributes the empty string. Phase 2 may
  default surrounding_context to a non-None value once the emitter
  carries source coordinates; until then, callers explicitly pass it
  in (or leave None for "no context"). The cache key's shape is the
  same in both cases — there's no schema bump on context-enable.
  """
  if not isinstance(slot_text, str):
    raise TypeError(f"slot_text must be str, got {type(slot_text).__name__}")
  if not isinstance(snippet_id, str):
    raise TypeError(
      f"snippet_id must be str, got {type(snippet_id).__name__}")
  if surrounding_context is None:
    surrounding_context = ""
  if not isinstance(surrounding_context, str):
    raise TypeError(
      f"surrounding_context must be str or None, got "
      f"{type(surrounding_context).__name__}")
  payload = (
    slot_text.encode("utf-8")
    + b"\x00"
    + snippet_id.encode("utf-8")
    + b"\x00"
    + surrounding_context.encode("utf-8")
  )
  return hashlib.sha256(payload).hexdigest()
