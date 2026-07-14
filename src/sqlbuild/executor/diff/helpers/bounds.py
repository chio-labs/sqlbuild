"""Bounded diff cursor helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlbuild.adapter.models import CursorValue
from sqlbuild.adapter.types import CursorKind
from sqlbuild.executor.diff.constants import (
    BOUNDED_DIFF_DAY_UNIT,
    BOUNDED_DIFF_HOUR_UNIT,
    BOUNDED_DIFF_MINUTE_UNIT,
)
from sqlbuild.executor.exceptions import ExecutorInputError


def resolve_bounded_cursors(
    *,
    model: Any,
    bounded: str | None,
) -> tuple[str | None, CursorValue | None, CursorValue | None, bool]:
    """Resolve cursor diff bounds, returning fallback flag when no cursor exists."""

    if bounded is None:
        return None, None, None, False
    cursor_column: str | None = _get_config_str(model=model, key="cursor")
    if cursor_column is None:
        return None, None, None, True
    cursor_type: str | None = _get_config_str(model=model, key="cursor_type")
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
    raise ExecutorInputError(f"model '{model.name}' bounded diff requires cursor_type", code="X101")


def _get_config_str(*, model: Any, key: str) -> str | None:
    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) and raw else None


def _parse_integer_bound(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as error:
        raise ExecutorInputError(
            "integer cursor bounded diff requires an integer bound",
            code="X102",
        ) from error


def _parse_duration_bound(raw: str) -> timedelta:
    bounded_value_part_count: int = 2
    if len(raw) < bounded_value_part_count:
        raise ExecutorInputError(
            "timestamp cursor bounded diff requires duration like 30d, 12h, or 15m",
            code="X103",
        )
    amount_text: str = raw[:-1]
    unit: str = raw[-1]
    try:
        amount: int = int(amount_text)
    except ValueError as error:
        raise ExecutorInputError(
            "timestamp cursor bounded diff requires duration like 30d, 12h, or 15m",
            code="X103",
        ) from error
    if amount <= 0:
        raise ExecutorInputError("bounded diff duration must be positive", code="X104")
    if unit == BOUNDED_DIFF_DAY_UNIT:
        return timedelta(days=amount)
    if unit == BOUNDED_DIFF_HOUR_UNIT:
        return timedelta(hours=amount)
    if unit == BOUNDED_DIFF_MINUTE_UNIT:
        return timedelta(minutes=amount)
    raise ExecutorInputError(
        "timestamp cursor bounded diff requires duration like 30d, 12h, or 15m",
        code="X103",
    )
