"""Expected planner-stage exception types."""

from __future__ import annotations


class PlannerInputError(ValueError):
    """Raised when planner inputs cannot be resolved safely."""

    code: str = "S000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
