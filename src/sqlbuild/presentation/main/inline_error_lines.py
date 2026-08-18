"""Public inline error-line formatting operation."""

from __future__ import annotations

from sqlbuild.presentation._helpers.error_text import (
    format_inline_error_lines as _format_inline_error_lines,
)
from sqlbuild.presentation.classes.cli_style import CliStyle


def format_inline_error_lines(
    *,
    error_code: str | None,
    error_message: str,
    error_help: str | None,
    content_width: int,
    style: CliStyle,
) -> list[str]:
    """Wrap an inline error to two display lines before truncating."""

    return _format_inline_error_lines(
        error_code=error_code,
        error_message=error_message,
        error_help=error_help,
        content_width=content_width,
        style=style,
    )
