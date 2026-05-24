"""Expected ingestr integration exception types."""

from __future__ import annotations


class IngestrIntegrationError(RuntimeError):
    """Raised when ingestr command construction or execution fails."""

    def __init__(self, message: str, run_result: object | None = None) -> None:
        super().__init__(message)
        self._run_result = run_result

    @property
    def run_result(self) -> object | None:
        return self._run_result
