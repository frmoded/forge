import os
import yaml


class SnippetRegistry:
  def __init__(self):
    self._snippets = {}

  def scan(self, vault_path):
    """Recursively crawl vault for .md files."""
    for root, _, files in os.walk(vault_path):
      for fname in files:
        if fname.endswith(".md"):
          self._index(os.path.join(root, fname))

  def _index(self, filepath):
    """Index snippet by title or filename fallback."""
    try:
      with open(filepath, encoding="utf-8") as f:
        content = f.read()
      meta, body = _parse_frontmatter(content)

      # Use 'title' from YAML or filename (without .md) as the ID
      snippet_id = meta.get("title") or os.path.splitext(
        os.path.basename(filepath))[0]

      if meta.get("type") in ("action", "data"):
        self._snippets[snippet_id] = {
          "meta": meta, "body": body, "path": filepath}
    except Exception:
      pass

  def get(self, snippet_id):
    return self._snippets.get(snippet_id)


class GraphResolver:
  def __init__(self, registry):
    self._registry = registry

  def resolve(self, snippet_id):
    return self._registry.get(snippet_id)


def _parse_frontmatter(content):
  """Split YAML frontmatter from body."""
  if not content.startswith("---"):
    return {}, content
  parts = content.split("---", 2)
  if len(parts) < 3:
    return {}, content
  try:
    meta = yaml.safe_load(parts[1]) or {}
  except Exception:
    meta = {}
  return meta, parts[2].strip()
