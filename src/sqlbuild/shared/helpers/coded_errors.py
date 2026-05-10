"""Helpers for SQLBuild expected errors with stable codes."""

from __future__ import annotations


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


def format_coded_error(*, code: str, message: str, help: str | None = None) -> str:
    """Render a result-stored coded error consistently with CLI expected errors."""

    rendered: str = f"error[{code}]: {message}"
    if help is not None:
        rendered = f"{rendered}\n  = help: {help}"
    return rendered
