"""Cursor algebra test data helpers."""

from datetime import datetime, timedelta, timezone


def build_temporal_values(*, positions: tuple[datetime, ...]) -> tuple[object, ...]:
    """Build date, timestamp, and offset timestamp values for each position."""

    values: list[object] = []
    for timestamp in positions:
        values.extend(
            (
                timestamp.date(),
                timestamp,
                timestamp.replace(tzinfo=timezone(timedelta(hours=5, minutes=30))),
            )
        )
    return tuple(values)
