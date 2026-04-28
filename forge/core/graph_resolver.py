from typing import Optional
from forge.core.snippet_registry import SnippetRegistry, BUILTIN_VAULT
from forge.core.exceptions import SnippetResolutionError


class GraphResolver:
  def __init__(self, registry: SnippetRegistry):
    self._registry = registry

  def resolve(self, snippet_id: str) -> dict:
    """Resolve a snippet reference per ADR 0002. Raises SnippetResolutionError on miss."""
    hit = self._lookup(snippet_id)
    if hit is None:
      raise SnippetResolutionError(reference=snippet_id, searched=self._searched_for(snippet_id))
    return hit

  def try_resolve(self, snippet_id: str) -> Optional[dict]:
    """Non-raising variant for callers that want to inspect on a miss."""
    return self._lookup(snippet_id)

  def _lookup(self, snippet_id: str) -> Optional[dict]:
    if "/" in snippet_id:
      vault_name, bare = snippet_id.split("/", 1)
      return self._registry.get_in_vault(vault_name, bare)
    return self._registry.get_bare(snippet_id)

  def _searched_for(self, snippet_id: str) -> list:
    if "/" in snippet_id:
      vault_name, _ = snippet_id.split("/", 1)
      return [vault_name]
    return [self._label(v) for v in self._registry.resolution_order()]

  @staticmethod
  def _label(vault_name: str) -> str:
    if vault_name == BUILTIN_VAULT:
      return "forge (built-in)"
    return vault_name
