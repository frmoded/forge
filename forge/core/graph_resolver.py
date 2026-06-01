from typing import Optional
from forge.core.snippet_registry import SnippetRegistry, BUILTIN_VAULT
from forge.core.exceptions import SnippetResolutionError


class GraphResolver:
  def __init__(self, registry: SnippetRegistry):
    self._registry = registry

  def resolve(self, snippet_id: str, caller_id: Optional[str] = None) -> dict:
    """Resolve a snippet reference per ADR 0002. Raises SnippetResolutionError on miss.

    When `caller_id` is provided AND it's a qualified ID with a subdir
    component (e.g. 'forge-music/blues/song'), bare references are
    probed against the caller's own directory FIRST. This makes
    `context.compute("chorus")` inside `forge-music/blues/song.md`
    resolve to `forge-music/blues/chorus` rather than missing all
    vaults. Falls back to the legacy bare walk on miss; the existing
    resolution-order contract is byte-identical for callers without
    `caller_id`.
    """
    hit = self._lookup(snippet_id, caller_id)
    if hit is None:
      raise SnippetResolutionError(reference=snippet_id, searched=self._searched_for(snippet_id))
    return hit

  def try_resolve(self, snippet_id: str, caller_id: Optional[str] = None) -> Optional[dict]:
    """Non-raising variant for callers that want to inspect on a miss."""
    return self._lookup(snippet_id, caller_id)

  def _lookup(self, snippet_id: str, caller_id: Optional[str] = None) -> Optional[dict]:
    if "/" in snippet_id:
      vault_name, bare = snippet_id.split("/", 1)
      return self._registry.get_in_vault(vault_name, bare)
    # Bare ref. Try caller-scoped sibling lookup first when applicable
    # (v0.2.26). TRY-FIRST, not TRY-ONLY — misses fall through to the
    # legacy resolution-order walk below.
    if caller_id is not None and "/" in caller_id:
      caller_vault, caller_bare = caller_id.split("/", 1)
      if "/" in caller_bare:
        caller_dir = caller_bare.rsplit("/", 1)[0]
        sibling = self._registry.get_in_vault(caller_vault, f"{caller_dir}/{snippet_id}")
        if sibling is not None:
          return sibling
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
