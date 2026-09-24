"""Strict janitor archive relation name grammar."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlbuild.adapter.relations.main.fit_artifact_logical_name import fit_artifact_logical_name
from sqlbuild.executor.janitor.constants import (
    ARCHIVE_ARTIFACT_LABEL,
    ARCHIVE_LOOKALIKE_PREFIX,
    ARCHIVE_NAME_PREFIX,
    ARCHIVE_NAME_SEPARATOR,
    ARCHIVE_TIMESTAMP_FORMAT,
)
from sqlbuild.executor.janitor.models import JanitorParsedArchiveName

_ARCHIVE_NAME_RE: re.Pattern[str] = re.compile(
    rf"^{re.escape(ARCHIVE_NAME_PREFIX)}"
    r"(?P<timestamp>[0-9]{8}T[0-9]{6}Z)"
    rf"{re.escape(ARCHIVE_NAME_SEPARATOR)}"
    r"(?P<logical_name>.+)$",
    re.IGNORECASE,
)


def archive_timestamp(value: datetime) -> datetime:
    """Normalize a timestamp to the UTC second resolution embedded in archive names."""

    aware: datetime = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.replace(microsecond=0)


def build_archive_name(*, original_name: str, archived_at: datetime, identifier_limit: int) -> str:
    """Build the fitted archive name, keeping the prefix and timestamp intact."""

    fixed_prefix: str = (
        f"{ARCHIVE_NAME_PREFIX}"
        f"{archive_timestamp(archived_at).strftime(ARCHIVE_TIMESTAMP_FORMAT)}"
        f"{ARCHIVE_NAME_SEPARATOR}"
    )
    logical_part: str = fit_artifact_logical_name(
        logical_name=original_name,
        fixed_prefix=fixed_prefix,
        identifier_limit=identifier_limit,
        artifact_label=ARCHIVE_ARTIFACT_LABEL,
    )
    return f"{fixed_prefix}{logical_part}"


def parse_archive_name(name: str) -> JanitorParsedArchiveName | None:
    """Parse a strict archive name, returning None for anything else."""

    match: re.Match[str] | None = _ARCHIVE_NAME_RE.fullmatch(name)
    if match is None:
        return None
    try:
        archived_at: datetime = datetime.strptime(
            match.group("timestamp").upper(), ARCHIVE_TIMESTAMP_FORMAT
        ).replace(tzinfo=UTC)
    except ValueError:
        return None
    return JanitorParsedArchiveName(
        archived_at=archived_at,
        logical_name=match.group("logical_name"),
    )


def is_archive_lookalike_name(name: str) -> bool:
    """Return whether a relation name is reserved for janitor archive handling."""

    return name.lower().startswith(ARCHIVE_LOOKALIKE_PREFIX)
