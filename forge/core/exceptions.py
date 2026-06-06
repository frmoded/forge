class SnippetResolutionError(Exception):
  """Raised when a snippet reference cannot be resolved.

  Carries the original reference and the list of sources searched so the
  caller can surface a structured error to the user (per ADR 0002).
  """

  def __init__(self, reference: str, searched: list):
    self.reference = reference
    self.searched = list(searched)
    super().__init__(self._format_message())

  def _format_message(self) -> str:
    if not self.searched:
      return f"Snippet '{self.reference}' not found."
    return f"Snippet '{self.reference}' not found. Searched: {', '.join(self.searched)}."


class AmbiguousSnippetResolutionError(Exception):
  """Raised by A4.1 Probe 2 (V2a v8) when a bare reference resolves to
  two or more sibling subdirs in the caller's vault. The author must
  qualify the reference (use `{vault}/{subdir}/{name}` form) to
  disambiguate.

  Carries the original bare reference and the full list of qualified
  candidate snippet_ids so callers (and the surfaced error message)
  can show every match explicitly.
  """

  def __init__(self, reference: str, candidates: list):
    self.reference = reference
    # Stored sorted for deterministic error messages and test stability.
    self.candidates = sorted(candidates)
    super().__init__(self._format_message())

  def _format_message(self) -> str:
    pretty = ", ".join(self.candidates)
    return (
      f"Bare reference '{self.reference}' is ambiguous across sibling "
      f"subdirs of the caller's vault. Candidates: {pretty}. "
      f"Qualify the reference to choose one."
    )
