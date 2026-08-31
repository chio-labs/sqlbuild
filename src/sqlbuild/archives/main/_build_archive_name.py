"""Archive-name builder entrypoint pending external integration."""

from datetime import datetime

from sqlbuild.archives._helpers.naming import build_archive_name as _build_archive_name


def build_archive_name(*, logical_name: str, archived_at: datetime, identifier_limit: int) -> str:
    """Build one fitted, timestamped SQLBuild archive name."""

    return _build_archive_name(
        logical_name=logical_name,
        archived_at=archived_at,
        identifier_limit=identifier_limit,
    )
