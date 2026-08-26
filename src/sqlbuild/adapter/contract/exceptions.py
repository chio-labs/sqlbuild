"""Expected adapter-facing exception types."""

from __future__ import annotations

from sqlbuild.sql_values.exceptions import SqlValueRenderingError


class AdapterUserError(ValueError):
    """Raised when adapter configuration or optional dependencies are invalid."""

    code: str = "A000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class UnsupportedTypedSqlRenderingError(AdapterUserError, SqlValueRenderingError):
    """Raised when an adapter cannot represent a requested typed SQL value."""

    def __init__(self, *, adapter_name: str, rendering: str, reason: str | None = None) -> None:
        reason_text: str = f": {reason}" if reason is not None else ""
        super().__init__(
            message=(
                f"adapter '{adapter_name}' does not support typed SQL {rendering} rendering"
                f"{reason_text}"
            )
        )
