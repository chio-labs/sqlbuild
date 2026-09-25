"""Expected model migration state exception types."""

from __future__ import annotations


class MigrationStateError(ValueError):
    """Raised when model migration state inputs or rows are invalid."""

    code: str = "M000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
