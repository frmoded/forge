import os
import yaml


class SnippetRegistry:
  def __init__(self):
    self._snippets = {}
    self.errors = []

  def scan(self, vault_path):
    self.errors = []
    for root, _, files in os.walk(vault_path):
      for fname in files:
        if fname.endswith(".md"):
          err = self._index(os.path.join(root, fname))
          if err:
            self.errors.append(err)

  def _index(self, filepath):
    try:
      with open(filepath, encoding="utf-8") as f:
        content = f.read()
      meta, body = _parse_frontmatter(content)
      snippet_id = os.path.splitext(os.path.basename(filepath))[0]
      if meta.get("type") in ("action", "data"):
        self._snippets[snippet_id] = {"meta": meta, "body": body, "path": filepath}
      return None
    except Exception as e:
      return f"{filepath}: {e}"

  def get(self, snippet_id):
    return self._snippets.get(snippet_id)


def _parse_frontmatter(content):
  if not content.startswith("---"):
    return {}, content
  parts = content.split("---", 2)
  if len(parts) < 3:
    return {}, content
  meta = yaml.safe_load(parts[1]) or {}
  return meta, parts[2].strip()
