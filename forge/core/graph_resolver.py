from forge.core.snippet_registry import SnippetRegistry


class GraphResolver:
  def __init__(self, registry: SnippetRegistry):
    self._registry = registry

  def resolve(self, snippet_id: str):
    return self._registry.get(snippet_id)
