"""Expected-error help extraction entrypoint."""

from __future__ import annotations


def error_help(error: BaseException) -> str | None:
    """Return expected-error help text when present."""

    help_text: object | None = getattr(error, "help", None)
    return help_text if isinstance(help_text, str) else None
