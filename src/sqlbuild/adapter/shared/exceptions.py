"""Expected adapter-facing exception types."""

from __future__ import annotations


class AdapterUserError(ValueError):
    """Raised when adapter configuration or optional dependencies are invalid."""

    code: str = "A000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
