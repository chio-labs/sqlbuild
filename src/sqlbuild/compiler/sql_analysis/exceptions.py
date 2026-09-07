"""SQL analysis boundary failures."""


class SqlAnalysisBoundaryError(RuntimeError):
    """Raised when the native analysis boundary returns an invalid payload."""
