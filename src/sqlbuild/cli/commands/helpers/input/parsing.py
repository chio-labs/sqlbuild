"""Neutral command input conversion."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def parse_cursor_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def parse_cursor_integer(value: str | None) -> int | None:
    if value is None:
        return None
    return int(Decimal(value))
