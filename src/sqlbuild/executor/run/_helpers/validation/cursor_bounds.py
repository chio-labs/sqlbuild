"""Runtime cursor bound resolution and sentinel substitution."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.executor.run.models import RuntimeCursorSpec

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
    target_database: str | None,
    target_schema: str | None,
    target_name: str,
    spec: RuntimeCursorSpec,
) -> CursorBounds | None:
    """Resolve concrete runtime cursor bounds from target and upstream relations."""

    cursor_type: str | None = spec.cursor_type
    upstream_parts: list[str] = []
    cursor_input: CursorInputRelation
    for cursor_input in spec.cursor_input_relations:
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
        target_database=target_database,
        target_schema=target_schema,
        target_name=target_name,
        cursor_column=spec.cursor_column,
    )

    derived_alias: str = " AS __cursor_bounds" if adapter.requires_derived_table_aliases() else ""
    sql: str = (
        "SELECT MIN(_min), MAX(_max) FROM ("
        + " UNION ALL ".join(upstream_parts)
        + f"){derived_alias}"
    )
    cursor: Any = adapter.execute(connection=connection, sql=sql)
    row: Any = cursor.fetchone()
    if row is None or row[1] is None:
        return None

    effective_grain: str | None = resolve_effective_timestamp_grain(
        cursor_type=cursor_type,
        downstream_grain=spec.cursor_grain,
        cursor_input_relations=spec.cursor_input_relations,
    )
    if cursor_type == CursorType.TIMESTAMP and effective_grain is not None:
        start_raw: object | None = target_max_raw if target_max_raw is not None else row[0]
        if start_raw is None:
            return None
        start: str | None = _normalize_bound(
            value=_floor_timestamp_bound(value=start_raw, grain=effective_grain), is_end=False
        )
        end: str | None = _normalize_bound(
            value=_increment_timestamp_bound(
                value=_floor_timestamp_bound(value=row[1], grain=effective_grain),
                grain=effective_grain,
            ),
            is_end=False,
        )
    else:
        start: str | None = (
            _normalize_bound(value=target_max_raw, is_end=False)
            if target_max_raw is not None
            else _normalize_bound(value=row[0], is_end=False)
        )
        end: str | None = _normalize_bound(value=row[1], is_end=True)
    if start is None or end is None:
        return None
    start = _apply_cursor_start_floor(
        current_start=start,
        cursor_start=spec.cursor_start,
        cursor_type=cursor_type,
    )
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
    target_database: str | None,
    target_schema: str | None,
    target_name: str,
    cursor_column: str,
) -> object | None:
    """Read the target cursor high-water mark or None when the target does not exist."""

    if not adapter.relation_exists(
        connection=connection,
        database=target_database,
        schema=target_schema,
        name=target_name,
    ):
        return None
    sql: str = f"SELECT MAX({cursor_column}) FROM {target_relation}"
    cursor: Any = adapter.execute(connection=connection, sql=sql)
    row: Any = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return row[0]


def _floor_timestamp_bound(*, value: object, grain: str) -> object:
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


def _increment_timestamp_bound(*, value: object, grain: str) -> object:
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
        final_month: int = 12
        year: int = value.year + (1 if value.month == final_month else 0)
        month: int = 1 if value.month == final_month else value.month + 1
        return value.replace(year=year, month=month, day=1)
    if grain == CursorGrain.YEAR:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value


def _normalize_bound(*, value: object, is_end: bool) -> str | None:
    if isinstance(value, datetime):
        normalized: datetime = value + timedelta(seconds=1) if is_end else value
        return normalized.isoformat()
    if isinstance(value, int):
        normalized_int: int = value + 1 if is_end else value
        return str(normalized_int)
    if value is None:
        return None
    return str(value)


def _apply_cursor_start_floor(
    *,
    current_start: str,
    cursor_start: str | None,
    cursor_type: str | None,
) -> str:
    if cursor_start is None:
        return current_start
    if cursor_type == CursorType.TIMESTAMP:
        current_timestamp: datetime | None = _try_parse_timestamp(current_start)
        floor_timestamp: datetime | None = _try_parse_timestamp(cursor_start)
        if current_timestamp is not None and floor_timestamp is not None:
            return max(current_timestamp, floor_timestamp).isoformat()
        return current_start
    if cursor_type == CursorType.INTEGER:
        current_integer: int | None = _try_parse_integer(current_start)
        floor_integer: int | None = _try_parse_integer(cursor_start)
        if current_integer is not None and floor_integer is not None:
            return str(max(current_integer, floor_integer))
    return current_start


def _try_parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _try_parse_integer(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
