"""SQLite timestamp text: the `YYYY-MM-DD HH:MM:SS` form SQLite's date functions produce."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlbuild.adapters.sqlite.constants import DATE_TIME_PATTERN, TIMESTAMP_TEXT_FORMAT

_DATE_TIME: re.Pattern[str] = re.compile(DATE_TIME_PATTERN)


def canonical_timestamp_text(value: str) -> str:
    """Rewrite an ISO-8601 date-time so text comparison orders it like SQLite timestamps."""

    if _DATE_TIME.match(value) is None:
        return value
    try:
        parsed: datetime = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    text: str = parsed.strftime(TIMESTAMP_TEXT_FORMAT)
    if parsed.microsecond:
        text += f".{parsed.microsecond:06d}".rstrip("0")
    return text
