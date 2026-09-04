"""Project specification exceptions."""

from __future__ import annotations


class SpecConfigError(RuntimeError):
    """Raised when project specification configuration is invalid."""


class ConfigValueTypeError(ValueError):
    """Raised when an authored config value has the wrong runtime type."""

    def __init__(self, *, key: str, expected: str, actual_type: type[object]) -> None:
        self.key = key
        self.expected = expected
        self.actual_type = actual_type
        super().__init__(f"config key '{key}' expected {expected}, got {actual_type.__name__}")
