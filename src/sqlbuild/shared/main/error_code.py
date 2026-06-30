"""Public expected-error code extraction entrypoint."""

from __future__ import annotations


def error_code(error: BaseException, *, fallback_code: str) -> str:
    """Return a stable error code from an expected exception-like object."""

    return str(getattr(error, "code", fallback_code))
