"""Cross-domain expected input errors."""

from __future__ import annotations


class SharedInputError(ValueError):
    """Raised when a public cross-domain input contract is invalid."""

    code: str = "G000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
