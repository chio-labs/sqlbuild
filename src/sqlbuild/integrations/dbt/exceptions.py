"""dbt interop exceptions."""

from __future__ import annotations


class DbtInteropError(ValueError):
    """Base class for expected dbt interop errors."""

    code: str = "C240"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class DbtInteropConfigError(DbtInteropError):
    """Raised when dbt project configuration is missing or invalid."""

    code: str = "C240"


class DbtInteropRuntimeError(DbtInteropError):
    """Raised when dbt command execution fails."""

    code: str = "C241"


class DbtInteropArgumentError(DbtInteropError):
    """Raised when `sqb dbt` arguments cannot be routed safely."""

    code: str = "C230"
