"""Edge snapshot storage (constitution F1-F4).

Snapshots live at <vault>/.forge/edges/<caller_id>/<callee_id>.md as markdown
files with frontmatter and a fenced wire-format body. Slashes in qualified
snippet IDs become subdirectory levels.

The path is hardcoded; configuration is YAGNI for v0.
"""

import os
import yaml
from datetime import datetime, timezone

from forge.core.serialization import serialize_for_wire
from forge.core.snippet_registry import parse_frontmatter

_EDGES_DIR = ".forge/edges"


def snapshot_path(vault_path, caller_id, callee_id):
  """Absolute path to the snapshot file for an edge. Does not check existence."""
  return os.path.join(vault_path, _EDGES_DIR, caller_id, callee_id + ".md")


def read_snapshot(vault_path, caller_id, callee_id):
  """Return {meta, body} for the snapshot, or None if no file exists."""
  path = snapshot_path(vault_path, caller_id, callee_id)
  if not os.path.isfile(path):
    return None
  with open(path, "r", encoding="utf-8") as f:
    content = f.read()
  meta, body = parse_frontmatter(content)
  return {"meta": meta, "body": body}


def write_snapshot(vault_path, caller_id, callee_id, value, callee_snippet=None):
  """Serialize `value` and overwrite the snapshot for this edge with state=live."""
  content_type, content_str = serialize_for_wire(value, callee_snippet)
  meta = {
    "type": "snapshot",
    "caller": caller_id,
    "callee": callee_id,
    "state": "live",
    "captured_at": _now_iso(),
    "content_type": content_type,
  }
  path = snapshot_path(vault_path, caller_id, callee_id)
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    f.write(_render(meta, content_type, content_str))


def set_snapshot_state(vault_path, caller_id, callee_id, state):
  """Flip the state field on an existing snapshot. Raises FileNotFoundError
  if the snapshot doesn't exist (per F5)."""
  path = snapshot_path(vault_path, caller_id, callee_id)
  if not os.path.isfile(path):
    raise FileNotFoundError(path)
  with open(path, "r", encoding="utf-8") as f:
    content = f.read()
  meta, body = parse_frontmatter(content)
  meta["state"] = state
  fm = yaml.dump(meta, sort_keys=False, default_flow_style=False).strip()
  with open(path, "w", encoding="utf-8") as f:
    f.write(f"---\n{fm}\n---\n\n{body}\n")


def _render(meta, content_type, content_str):
  fm = yaml.dump(meta, sort_keys=False, default_flow_style=False).strip()
  return f"---\n{fm}\n---\n\n```{content_type}\n{content_str}\n```\n"


def _now_iso():
  return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
