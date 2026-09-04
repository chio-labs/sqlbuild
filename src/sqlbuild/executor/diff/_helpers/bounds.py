"""Bounded diff cursor helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.models import CursorValue
from sqlbuild.adapter.contract.types import CursorKind
from sqlbuild.compiler.planner.models import Duration
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.spec.contracts.main.get_config_str import get_config_str


def resolve_bounded_cursors(
    *,
    model: Any,
    bounded: str | None,
) -> tuple[str | None, CursorValue | None, CursorValue | None, bool]:
    """Resolve cursor diff bounds, returning fallback flag when no cursor exists."""

    if bounded is None:
        return None, None, None, False
    cursor_column: str | None = get_config_str(values=model.config.values, key="cursor")
    if cursor_column is None:
        return None, None, None, True
    cursor_type: str | None = get_config_str(values=model.config.values, key="cursor_type")
    if cursor_type == CursorKind.INTEGER:
        return (
            cursor_column,
            CursorValue(kind=CursorKind.INTEGER, value=_parse_integer_bound(bounded)),
            None,
            False,
        )
    if cursor_type == CursorKind.TIMESTAMP:
        end: datetime = datetime.now(tz=UTC)
        start: datetime = _parse_duration_bound(bounded).subtract_from(end)
        return (
            cursor_column,
            CursorValue(kind=CursorKind.TIMESTAMP, value=start),
            CursorValue(kind=CursorKind.TIMESTAMP, value=end),
            False,
        )
    raise ExecutorInputError(f"model '{model.name}' bounded diff requires cursor_type", code="X101")


def _parse_integer_bound(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as error:
        raise ExecutorInputError(
            "integer cursor bounded diff requires an integer bound",
            code="X102",
        ) from error


def _parse_duration_bound(raw: str) -> Duration:
    duration: Duration | None = Duration.parse(raw)
    if duration is None:
        raise ExecutorInputError(
            "timestamp cursor bounded diff requires duration like 30d, 12h, 15m, or 1mo",
            code="X103",
        )
    return duration
