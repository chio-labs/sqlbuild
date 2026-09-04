"""Tolerantly parse a typed cursor scalar."""

from sqlbuild.cursor_algebra._helpers.parsing import parse_scalar
from sqlbuild.cursor_algebra.types import CursorScalar


def try_parse(*, raw: object, cursor_type: str) -> CursorScalar | None:
    """Parse discovery values which may be DATE or TIMESTAMP values."""

    try:
        return parse_scalar(raw=raw, cursor_type=cursor_type)
    except (TypeError, ValueError):
        return None
