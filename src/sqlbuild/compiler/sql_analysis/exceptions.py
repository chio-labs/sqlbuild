"""SQL analysis boundary failures."""


class UnsupportedLexicalSyntaxError(ValueError):
    """Raised when an adapter declares lexical rules the native SQL scanners do not support."""
