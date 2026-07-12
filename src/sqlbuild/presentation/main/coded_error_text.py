"""Public coded-error formatting entry."""

from __future__ import annotations

from sqlbuild.presentation.helpers.error_text import format_coded_error as _format_coded_error


def format_coded_error(
    *, code: str, message: str, help: str | None = None, use_color: bool = False
) -> str:
    """Render a result-stored coded error consistently with CLI expected errors."""

    return _format_coded_error(code=code, message=message, help=help, use_color=use_color)
