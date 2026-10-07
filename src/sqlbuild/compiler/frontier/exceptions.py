"""Compiler engine selection errors."""


class CompilerEngineError(ValueError):
    """Raised when the requested compiler engine is not a supported value."""


class NativeStageMismatchError(RuntimeError):
    """Raised when a native stage and the Python compiler disagree about one input."""
