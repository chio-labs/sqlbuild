"""Project temporal cursor bounds onto comparable datetimes."""

from datetime import UTC, datetime

from sqlbuild.cursor_algebra.models import DateValue, TimestampValue


def aligned_timestamp_bounds(
    *, start: DateValue | TimestampValue, end: DateValue | TimestampValue
) -> tuple[datetime, datetime]:
    """Return comparable bounds, presuming a naive side UTC when the other is aware."""

    start_at: datetime = _as_datetime(value=start)
    end_at: datetime = _as_datetime(value=end)
    if (start_at.tzinfo is None) != (end_at.tzinfo is None):
        start_at = _presume_utc(value=start_at)
        end_at = _presume_utc(value=end_at)
    return start_at, end_at


def _as_datetime(*, value: DateValue | TimestampValue) -> datetime:
    if isinstance(value, TimestampValue):
        return value.value
    return datetime.combine(value.value, datetime.min.time())


def _presume_utc(*, value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
