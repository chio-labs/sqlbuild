"""Bounded diff cursor helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlbuild.adapter.shared.models import CursorValue
from sqlbuild.adapter.shared.types import CursorKind


def resolve_bounded_cursors(
    *,
    model: Any,
    bounded: str | None,
) -> tuple[str | None, CursorValue | None, CursorValue | None, bool]:
    """Resolve cursor diff bounds, returning fallback flag when no cursor exists."""

    if bounded is None:
        return None, None, None, False
    cursor_column: str | None = _get_config_str(model, "cursor")
    if cursor_column is None:
        return None, None, None, True
    cursor_type: str | None = _get_config_str(model, "cursor_type")
    if cursor_type == CursorKind.INTEGER:
        return (
            cursor_column,
            CursorValue(kind=CursorKind.INTEGER, value=_parse_integer_bound(bounded)),
            None,
            False,
        )
    if cursor_type == CursorKind.TIMESTAMP:
        end: datetime = datetime.now(tz=UTC)
        start: datetime = end - _parse_duration_bound(bounded)
        return (
            cursor_column,
            CursorValue(kind=CursorKind.TIMESTAMP, value=start),
            CursorValue(kind=CursorKind.TIMESTAMP, value=end),
            False,
        )
    raise ValueError(f"model '{model.name}' bounded diff requires cursor_type")


def _get_config_str(model: Any, key: str) -> str | None:
    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) and raw else None


def _parse_integer_bound(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError("integer cursor bounded diff requires an integer bound") from error


def _parse_duration_bound(raw: str) -> timedelta:
    if len(raw) < 2:
        raise ValueError("timestamp cursor bounded diff requires duration like 30d, 12h, or 15m")
    amount_text: str = raw[:-1]
    unit: str = raw[-1]
    try:
        amount: int = int(amount_text)
    except ValueError as error:
        raise ValueError(
            "timestamp cursor bounded diff requires duration like 30d, 12h, or 15m"
        ) from error
    if amount <= 0:
        raise ValueError("bounded diff duration must be positive")
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    raise ValueError("timestamp cursor bounded diff requires duration like 30d, 12h, or 15m")
