"""dbt interop exceptions."""

from __future__ import annotations


class DbtInteropArgumentError(ValueError):
    """Raised when `sqb dbt` arguments cannot be routed safely."""

    code: str = "C230"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
