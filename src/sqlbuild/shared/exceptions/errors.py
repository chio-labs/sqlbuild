"""Expected shared helper errors."""

from __future__ import annotations


class SharedInputError(ValueError):
    """Raised when shared helper inputs are invalid."""

    code: str = "G000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
