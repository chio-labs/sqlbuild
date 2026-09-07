"""Column-lineage failures."""


class LineageAnalysisError(RuntimeError):
    """Raised when the native lineage boundary returns an invalid payload."""
