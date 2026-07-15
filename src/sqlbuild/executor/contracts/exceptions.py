"""Expected executor-stage exception types."""

from __future__ import annotations


class ExecutorInputError(ValueError):
    """Raised when runtime execution inputs are invalid."""

    code: str = "X000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class ExecutorJsonTypeError(TypeError):
    """Raised when executor JSON serialization receives an unsupported value."""

    code: str = "X000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
