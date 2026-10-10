"""SQL analysis boundary failures."""


class SqlAnalysisBoundaryError(RuntimeError):
    """Raised when the native analysis boundary returns an invalid payload."""


class UnsupportedLexicalSyntaxError(ValueError):
    """Raised when an adapter declares lexical rules the native SQL scanners do not support."""
