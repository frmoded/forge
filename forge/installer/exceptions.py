class ForgeError(Exception):
  """Base for all installer/registry/manifest errors."""


class NetworkError(ForgeError):
  """Connection-level failure (DNS, refused, reset, etc.)."""


class TimeoutError(ForgeError):
  """Request exceeded the configured timeout."""


class HttpError(ForgeError):
  """Non-2xx HTTP response."""

  def __init__(self, message: str, status_code: int):
    super().__init__(message)
    self.status_code = status_code


class HashMismatchError(ForgeError):
  """SHA-256 of file did not match the expected digest."""

  def __init__(self, actual: str, expected: str):
    super().__init__(f"hash mismatch: actual={actual} expected={expected}")
    self.actual = actual
    self.expected = expected


class PathTraversalError(ForgeError):
  """Tarball contained an unsafe path (.. or absolute)."""


class ValidationError(ForgeError):
  """Schema validation failure (registry index or vault manifest)."""


class SnippetNotFoundError(ForgeError):
  """Vault or version not present in registry."""
