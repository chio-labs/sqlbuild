"""Runtime cursor bound resolution and sentinel substitution."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation
from sqlbuild.compiler.planner.types import CursorGrain, CursorType

_TIMESTAMP_GRAIN_ORDER: dict[str, int] = {
    CursorGrain.SECOND: 0,
    CursorGrain.MINUTE: 1,
    CursorGrain.HOUR: 2,
    CursorGrain.DAY: 3,
    CursorGrain.MONTH: 4,
    CursorGrain.YEAR: 5,
}


def has_model_backed_cursor_inputs(
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> bool:
    """Return whether any cursor input relation is backed by another model."""

    return any(relation.is_model_backed for relation in cursor_input_relations)


def resolve_runtime_cursor_bounds(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_relation: str,
    cursor_column: str,
    cursor_type: str | None,
    cursor_grain: str | None,
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> CursorBounds | None:
    """Resolve concrete runtime cursor bounds from target and upstream relations."""

    upstream_parts: list[str] = []
    cursor_input: CursorInputRelation
    for cursor_input in cursor_input_relations:
        upstream_parts.append(
            f"SELECT MIN({cursor_input.cursor_column}) AS _min, "
            f"MAX({cursor_input.cursor_column}) AS _max FROM {cursor_input.relation}"
        )
    if not upstream_parts:
        return None

    target_max_raw: object | None = _query_target_max_raw(
        adapter=adapter,
        connection=connection,
        target_relation=target_relation,
        cursor_column=cursor_column,
    )

    sql: str = "SELECT MIN(_min), MAX(_max) FROM (" + " UNION ALL ".join(upstream_parts) + ")"
    cursor: Any = adapter.execute(connection, sql)
    row: Any = cursor.fetchone()
    if row is None or row[1] is None:
        return None

    effective_grain: str | None = resolve_effective_timestamp_grain(
        cursor_type=cursor_type,
        downstream_grain=cursor_grain,
        cursor_input_relations=cursor_input_relations,
    )
    if cursor_type == CursorType.TIMESTAMP and effective_grain is not None:
        start_raw: object | None = target_max_raw if target_max_raw is not None else row[0]
        if start_raw is None:
            return None
        start: str | None = _normalize_bound(
            _floor_timestamp_bound(start_raw, effective_grain), is_end=False
        )
        end: str | None = _normalize_bound(
            _increment_timestamp_bound(
                _floor_timestamp_bound(row[1], effective_grain), effective_grain
            ),
            is_end=False,
        )
    else:
        start: str | None = (
            _normalize_bound(target_max_raw, is_end=False)
            if target_max_raw is not None
            else _normalize_bound(row[0], is_end=False)
        )
        end: str | None = _normalize_bound(row[1], is_end=True)
    if start is None or end is None:
        return None
    return CursorBounds(start=start, end=end)


def resolve_effective_timestamp_grain(
    *,
    cursor_type: str | None,
    downstream_grain: str | None,
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> str | None:
    """Return the coarsest timestamp grain participating in runtime-owned replay."""

    if cursor_type != CursorType.TIMESTAMP:
        return None
    effective: str = downstream_grain or CursorGrain.SECOND
    cursor_input: CursorInputRelation
    for cursor_input in cursor_input_relations:
        input_grain: str = cursor_input.cursor_grain or CursorGrain.SECOND
        if _TIMESTAMP_GRAIN_ORDER[input_grain] > _TIMESTAMP_GRAIN_ORDER[effective]:
            effective = input_grain
    return effective


def substitute_cursor_sentinels(*, sql: str, bounds: CursorBounds) -> str:
    """Substitute runtime cursor sentinels with concrete bounds."""

    result: str = sql.replace(MICROBATCH_START_SENTINEL, bounds.start)
    return result.replace(MICROBATCH_END_SENTINEL, bounds.end)


def _query_target_max_raw(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_relation: str,
    cursor_column: str,
) -> object | None:
    sql: str = f"SELECT MAX({cursor_column}) FROM {target_relation}"
    try:
        cursor: Any = adapter.execute(connection, sql)
    except Exception:
        return None
    row: Any = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return row[0]


def _floor_timestamp_bound(value: object, grain: str) -> object:
    if not isinstance(value, datetime):
        return value
    if grain == CursorGrain.SECOND:
        return value.replace(microsecond=0)
    if grain == CursorGrain.MINUTE:
        return value.replace(second=0, microsecond=0)
    if grain == CursorGrain.HOUR:
        return value.replace(minute=0, second=0, microsecond=0)
    if grain == CursorGrain.DAY:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if grain == CursorGrain.MONTH:
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if grain == CursorGrain.YEAR:
        return value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return value


def _increment_timestamp_bound(value: object, grain: str) -> object:
    if not isinstance(value, datetime):
        return value
    if grain == CursorGrain.SECOND:
        return value + timedelta(seconds=1)
    if grain == CursorGrain.MINUTE:
        return value + timedelta(minutes=1)
    if grain == CursorGrain.HOUR:
        return value + timedelta(hours=1)
    if grain == CursorGrain.DAY:
        return value + timedelta(days=1)
    if grain == CursorGrain.MONTH:
        year: int = value.year + (1 if value.month == 12 else 0)
        month: int = 1 if value.month == 12 else value.month + 1
        return value.replace(year=year, month=month, day=1)
    if grain == CursorGrain.YEAR:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value


def _normalize_bound(value: object, *, is_end: bool) -> str | None:
    if isinstance(value, datetime):
        normalized: datetime = value + timedelta(seconds=1) if is_end else value
        return normalized.isoformat()
    if isinstance(value, int):
        normalized_int: int = value + 1 if is_end else value
        return str(normalized_int)
    if value is None:
        return None
    return str(value)
