"""Expected fingerprint storage exception types."""

from __future__ import annotations


class FingerprintInputError(ValueError):
    """Raised when fingerprint storage inputs or rows are invalid."""

    code: str = "F000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
