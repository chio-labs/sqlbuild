"""Public coded-error formatting entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.error_text import format_coded_error as _format_coded_error


def format_coded_error(
    *,
    code: str,
    message: str,
    help: str | None = None,
    use_color: bool = False,
    include_error_label: bool = True,
) -> str:
    """Render a result-stored coded error consistently with CLI expected errors."""

    return _format_coded_error(
        code=code,
        message=message,
        help=help,
        use_color=use_color,
        include_error_label=include_error_label,
    )
