"""Column-lineage failures."""


class LineageAnalysisError(RuntimeError):
    """Raised when the native lineage boundary returns an invalid payload."""


class UnknownLineageDialectError(ValueError):
    """Raised, as Python's parser raised `ValueError`, for a dialect Polyglot does not know."""
