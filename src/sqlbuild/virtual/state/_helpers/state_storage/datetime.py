"""Virtual-state naive UTC wall-clock datetime boundary helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def to_naive_utc_wall_clock(value: datetime) -> datetime:
    """Encode an application datetime for a naive UTC virtual-state TIMESTAMP column."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def from_naive_utc_wall_clock(value: datetime) -> datetime:
    """Decode a naive UTC virtual-state TIMESTAMP as an aware UTC datetime."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
