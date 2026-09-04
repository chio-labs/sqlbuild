"""Source freshness datetime invariant helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError


def require_aware_utc_datetime(*, value: datetime, field_name: str) -> datetime:
    """Require an aware freshness datetime and normalize it to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise SourceFreshnessObservationError(
            f"source freshness {field_name} must be timezone-aware"
        )
    return value.astimezone(UTC)


def normalize_presumed_utc_datetime(*, value: datetime) -> datetime:
    """Treat a naive adapter or legacy-state datetime as UTC and normalize aware values."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
