"""Public janitor archive naming for relations archived outside the janitor."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.executor.janitor._helpers.archive_names import build_archive_name


def build_janitor_archive_name(
    *, original_name: str, archived_at: datetime, identifier_limit: int, kind: str
) -> str:
    """Build a strict archive name that janitor expires by its embedded timestamp."""

    return build_archive_name(
        original_name=original_name,
        archived_at=archived_at,
        identifier_limit=identifier_limit,
        kind=kind,
    )
