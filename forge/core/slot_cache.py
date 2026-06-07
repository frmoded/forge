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
import json
import re

import yaml


class SlotCacheMissError(Exception):
  """Raised by the engine resolver when a `{{ ... }}` slot is not in
  the snippet's # Slots cache.

  Carries a list of `missing` entries — each a dict
  `{"slot_text": str, "snippet_id": str, "surrounding_context": str}`
  in document order so the plugin can batch them into a single
  /resolve-slot call.

  v0.2.70 — Phase 2 wiring. Per the design's two-pass cache-miss
  seam, the engine raises this on first miss; the resolver's caller
  in `resolve_action_code` lets it propagate to the plugin
  orchestration layer (via the Pyodide error boundary). The plugin
  catches, calls /resolve-slot, writes the responses back to the
  snippet's # Slots heading, and re-fires the transpile gesture.

  Per E-- spec §1.2 — LLM calls are transpile-time only. At runtime,
  this error must NOT be caught and silently resolved; the user
  re-fires the Forge-click and the second pass is a clean cache hit.
  """

  def __init__(self, missing):
    self.missing = missing
    # Encode the missing list as JSON in the message so the
    # Pyodide → JS exception boundary preserves the structure (Pyodide
    # surfaces the str of the exception as the JS Error message).
    super().__init__(json.dumps({"slot_cache_miss": missing}))


def compute_english_hash(english_text):
  """v0.2.72 — stable hash of an English facet for cache invalidation
  per B7.3.

  Normalizes whitespace before hashing so cosmetic edits (trailing
  spaces, leading/trailing blank lines) don't churn the cache:

    - Trim trailing whitespace from each line.
    - Strip leading and trailing fully-blank lines.
    - Internal blank lines preserved (paragraph breaks matter).

  Returns hex-encoded sha256 of the normalized text encoded as UTF-8.

  Determinism is a HARD requirement — same inputs MUST produce the
  same output across Python versions and platforms. The TypeScript
  helper at src/english-hash-core.ts mirrors this implementation
  byte-for-byte; the cross-language hardcoded-expectation test pins
  parity.

  Tolerant of None / empty input: returns the hash of the empty
  string in both cases so callers don't have to special-case.
  """
  if english_text is None:
    english_text = ""
  if not isinstance(english_text, str):
    raise TypeError(
      f"english_text must be str or None, got "
      f"{type(english_text).__name__}")
  # Trim trailing whitespace per line.
  lines = [line.rstrip() for line in english_text.split("\n")]
  # Strip leading + trailing fully-blank lines.
  while lines and lines[0] == "":
    lines.pop(0)
  while lines and lines[-1] == "":
    lines.pop()
  normalized = "\n".join(lines)
  return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_engine_slot_resolver(snippet_id, slot_cache, missing_collector):
  """Build a `resolve(slot_text) -> str` callable for E--'s
  `transpile(source, resolve_slot=...)` interface.

  Parameters:
  - `snippet_id`: identifies the calling snippet for cache keying +
     plugin-side LLM context routing.
  - `slot_cache`: dict of cache_key → python_expr (from
     parse_slots_section on the snippet body). Read-only here.
  - `missing_collector`: a mutable list the resolver appends to on
     each cache miss. After transpile returns, the caller inspects
     this list and raises SlotCacheMissError with the full set if
     non-empty.

  Behavior on cache hit: returns the cached python_expr.
  Behavior on cache miss: appends a dict
    `{"slot_text": ..., "snippet_id": ..., "surrounding_context": ""}`
  to `missing_collector` AND returns a `None` sentinel python_expr
  so transpile can continue scanning. The generated Python from a
  partial-cache transpile is never returned to the caller — the
  caller raises SlotCacheMissError instead — but the resolver must
  return a valid string so E--'s emitter doesn't crash mid-walk.

  This single-pass collection is load-bearing for delta #2 (batched
  /resolve-slot): one transpile pass surfaces ALL missing slots so
  the plugin can batch them into one round-trip, not N.

  Per delta #1 (Phase 2 prompt §0): the cache key is
  `(slot_text, snippet_id)` only — `surrounding_context` flows in
  the LLM request for disambiguation but NOT in the cache key. This
  preserves freeze semantics: prose edits to surrounding lines must
  not invalidate previously-resolved slots.

  v0.2.70 — Phase 2 wiring.
  """
  # Sentinel value spliced into the partial-transpile output when a
  # slot is missing. Never reaches the caller (caller raises instead)
  # but must be a valid Python expression so emit() doesn't blow up.
  _MISS_SENTINEL = "None"

  def resolve(slot_text):
    key = compute_slot_cache_key(slot_text, snippet_id)
    if key in slot_cache:
      return slot_cache[key]
    missing_collector.append({
      "slot_text": slot_text,
      "snippet_id": snippet_id,
      "surrounding_context": "",
    })
    return _MISS_SENTINEL
  return resolve


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
