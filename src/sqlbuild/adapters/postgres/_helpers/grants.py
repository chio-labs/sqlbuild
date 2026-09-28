"""Render PostgreSQL privileges replayed onto a compatibility view."""

from __future__ import annotations


def render_postgres_grant(
    *, privilege: str, grantee: str | None, grantable: bool, destination: str
) -> str:
    """Render one table privilege of the archived relation as a grant on ``destination``."""

    option: str = " WITH GRANT OPTION" if grantable else ""
    return f"GRANT {privilege} ON {destination} TO {grantee or 'PUBLIC'}{option}"
