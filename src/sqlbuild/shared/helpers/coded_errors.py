"""Helpers for SQLBuild expected errors with stable codes."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.shared.helpers.colors import dim, red_bold


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

    prefix: str = _style(f"error[{code}]:", red_bold, use_color=use_color)
    rendered: str = f"{prefix} {message}"
    if help is not None:
        help_label: str = _style("= help:", dim, use_color=use_color)
        rendered = f"{rendered}\n  {help_label} {help}"
    return rendered


def _style(text: str, styler: Callable[[str], str], *, use_color: bool) -> str:
    if not use_color:
        return text
    return styler(text)
