"""Relation catalog timestamp normalization entrypoint."""

from __future__ import annotations

from datetime import UTC, datetime


def relation_age_timestamp_utc(value: object) -> datetime | None:
    """Return one catalog timestamp as aware UTC, treating offset-free values as UTC."""

    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
