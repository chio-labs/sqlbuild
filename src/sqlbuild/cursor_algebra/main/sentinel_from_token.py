"""Parse a typed cursor sentinel."""

from sqlbuild.cursor_algebra.types import BoundSentinel


def sentinel_from_token(*, token: str) -> BoundSentinel | None:
    """Parse a SQL token as a typed sentinel when recognized."""

    try:
        return BoundSentinel(token)
    except ValueError:
        return None
