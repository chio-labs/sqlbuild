"""Compiler frontier errors."""


class NativeStageMismatchError(RuntimeError):
    """Raised when native state the compiler replays is inconsistent with its inputs."""
