"""Expected-error message extraction entrypoint."""

from __future__ import annotations


def error_message(error: BaseException) -> str:
    """Return a stable message from an expected exception-like object."""

    return str(getattr(error, "message", str(error)))
