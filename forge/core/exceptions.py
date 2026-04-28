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
