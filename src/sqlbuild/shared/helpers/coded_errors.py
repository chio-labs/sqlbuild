"""Helpers for SQLBuild expected errors with stable codes."""

from __future__ import annotations

from sqlbuild.shared.helpers.cli_style import CliStyle


def error_code(error: BaseException, *, fallback_code: str) -> str:
    """Return a stable error code from an expected exception-like object."""

    return str(getattr(error, "code", fallback_code))


def error_message(error: BaseException) -> str:
    """Return a stable message from an expected exception-like object."""

    return str(getattr(error, "message", str(error)))


def error_help(error: BaseException) -> str | None:
    """Return expected-error help text when present."""

    help_text: object | None = getattr(error, "help", None)
    return help_text if isinstance(help_text, str) else None


def format_coded_error(
    *, code: str, message: str, help: str | None = None, use_color: bool = False
) -> str:
    """Render a result-stored coded error consistently with CLI expected errors."""

    style: CliStyle = CliStyle(use_color=use_color)
    prefix: str = style.error_strong(f"error[{code}]:")
    rendered_message: str = _format_error_message(message=message, style=style)
    rendered: str = f"{prefix} {rendered_message}"
    if help is not None:
        help_label: str = style.muted("= help:")
        rendered = f"{rendered}\n  {help_label} {help}"
    return rendered


def _format_error_message(*, message: str, style: CliStyle) -> str:
    lines: list[str] = message.split("\n")
    if len(lines) == 1:
        return message
    first_line: str = lines[0]
    continuation_lines: list[str] = [style.muted(line) for line in lines[1:]]
    return "\n".join([first_line, *continuation_lines])
