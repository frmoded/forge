import os
from pathlib import Path
from typing import List, Optional
from forge.core.snippet_registry import parse_frontmatter, BUILTIN_VAULT

_SNIPPETS_ROOT = Path(__file__).parent / "snippets"


def load_builtin_vault(snippets_root: Optional[Path] = None) -> List[dict]:
  """Walk the builtin snippets directory, parse each .md, return tagged dicts.

  Each returned dict carries:
    - meta, body              from the existing parser
    - path                    absolute filesystem path
    - vault                   "forge"
    - source                  "builtin"
    - snippet_id              "forge/<relative-path-with-slashes>" (no .md)

  Files lacking type=action|data are skipped silently (matches filesystem
  scan behavior). Parse errors propagate — a malformed builtin is a
  package bug that should fail loud at startup.
  """
  root = Path(snippets_root) if snippets_root is not None else _SNIPPETS_ROOT
  if not root.is_dir():
    return []

  snippets: List[dict] = []
  for dirpath, _, filenames in os.walk(root):
    for fname in sorted(filenames):
      if not fname.endswith(".md"):
        continue
      filepath = Path(dirpath) / fname
      with open(filepath, encoding="utf-8") as f:
        content = f.read()
      meta, body = parse_frontmatter(content)
      if meta.get("type") not in ("action", "data"):
        continue
      bare = _bare_id(filepath, root)
      snippets.append({
        "meta": meta,
        "body": body,
        "path": str(filepath),
        "vault": BUILTIN_VAULT,
        "source": "builtin",
        "snippet_id": f"{BUILTIN_VAULT}/{bare}",
      })
  return snippets


def _bare_id(filepath: Path, root: Path) -> str:
  rel = filepath.relative_to(root)
  no_ext = rel.with_suffix("")
  # forward slashes regardless of OS
  return "/".join(no_ext.parts)
