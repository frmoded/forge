"""Error types for the E-- deterministic core."""


class EmmSyntaxError(Exception):
    """Raised for any syntax violation in canonical E-- source."""
    pass


class EmmResolveError(Exception):
    """Raised when a {{ }} LLM value slot cannot be resolved.

    Covers a missing API key on a cache miss and model output that is not a
    valid Python expression.
    """
    pass


class EmmNormalizeError(Exception):
    """Raised when free-English E-- cannot be normalized to canonical.

    Covers a missing API key on a cache miss and model output that does not
    parse as canonical E-- (the normalizer validates by re-parsing and refuses
    to accept un-parseable "canonical").
    """
    pass
