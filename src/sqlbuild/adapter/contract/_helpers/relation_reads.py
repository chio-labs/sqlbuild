"""Normalize warehouse values in relation usage rows."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_datetime(value: object) -> datetime:
    """A warehouse timestamp as an aware UTC datetime; naive values are taken as UTC."""

    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
