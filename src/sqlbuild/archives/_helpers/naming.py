"""Portable same-schema archive names."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlbuild.archives.constants import ARCHIVE_NAME_PREFIX, ARCHIVE_TIMESTAMP_FORMAT
from sqlbuild.archives.exceptions import ArchiveStateError
from sqlbuild.archives.models import ParsedArchiveName
from sqlbuild.compiler.planner.main.scenarios.fit_artifact_logical_name import (
    fit_artifact_logical_name,
)

_ARCHIVE_NAME_RE: re.Pattern[str] = re.compile(
    rf"^{re.escape(ARCHIVE_NAME_PREFIX)}"
    r"(?P<timestamp>[0-9]{8}T[0-9]{12}Z)__"
    r"(?P<logical_name>.+)$",
    flags=re.IGNORECASE,
)


def build_archive_name(*, logical_name: str, archived_at: datetime, identifier_limit: int) -> str:
    """Build a timestamped archive name fitted to one adapter's identifier limit."""

    normalized_at: datetime = archived_at.astimezone(UTC)
    fixed_prefix: str = f"{ARCHIVE_NAME_PREFIX}{normalized_at.strftime(ARCHIVE_TIMESTAMP_FORMAT)}__"
    fitted_name: str = fit_artifact_logical_name(
        logical_name=logical_name,
        fixed_prefix=fixed_prefix,
        identifier_limit=identifier_limit,
        artifact_label="Archive",
    )
    return f"{fixed_prefix}{fitted_name}"


def parse_archive_name(name: str) -> ParsedArchiveName | None:
    """Parse strict SQLBuild archive names without relying on state metadata."""

    match: re.Match[str] | None = _ARCHIVE_NAME_RE.fullmatch(name)
    if match is None:
        return None
    try:
        archived_at: datetime = datetime.strptime(
            match.group("timestamp"), ARCHIVE_TIMESTAMP_FORMAT
        ).replace(tzinfo=UTC)
    except ValueError as error:
        raise ArchiveStateError(f"Invalid archive timestamp in {name!r}") from error
    return ParsedArchiveName(
        archived_at=archived_at,
        logical_name=match.group("logical_name"),
    )
