"""Parse a typed cursor scalar."""

from sqlbuild.cursor_algebra._helpers.parsing import parse_scalar
from sqlbuild.cursor_algebra.types import CursorScalar


def parse(*, raw: object, cursor_type: str) -> CursorScalar:
    """Parse one cursor scalar, preserving date-ness and timestamp offsets."""

    return parse_scalar(raw=raw, cursor_type=cursor_type)
