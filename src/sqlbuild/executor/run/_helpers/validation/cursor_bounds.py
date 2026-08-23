"""Runtime cursor bound resolution and sentinel substitution."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.cursor_intrinsics import resolve_cursor_intrinsics
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.main.execution.cursor_replay_policy import apply_cursor_replay_policy
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation, ModelPlanEntry
from sqlbuild.compiler.planner.types import BackfillAction, CursorGrain, CursorType
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
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


def build_runtime_cursor_spec(
    *, entry: ModelPlanEntry, read_destination_cursor: bool = True
) -> RuntimeCursorSpec:
    """Build runtime cursor policy from the corresponding immutable model plan entry."""

    if entry.cursor_column is None:
        raise ExecutorInputError("runtime-owned cursor resolution requires cursor_column")
    return RuntimeCursorSpec(
        cursor_column=entry.cursor_column,
        cursor_type=entry.cursor_type,
        cursor_grain=entry.cursor_grain,
        cursor_start=entry.cursor_start,
        cursor_input_relations=entry.cursor_input_relations,
        start_cursor_override=entry.start_cursor_override,
        end_cursor_override=entry.end_cursor_override,
        lookback=entry.lookback,
        backfill_duration=(
            entry.backfill.duration
            if entry.backfill.action == BackfillAction.BOUNDED
            else None
        ),
        read_destination_cursor=read_destination_cursor,
    )


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

    target_max_raw: object | None = None
    if spec.read_destination_cursor:
        target_max_raw = _query_target_max_raw(
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
        "SELECT MIN(_min), CASE WHEN COUNT(*) = COUNT(_max) THEN MIN(_max) END FROM ("
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
    if spec.end_cursor_override is not None:
        end = _apply_cursor_end_ceiling(
            current_end=end,
            end_cursor_override=spec.end_cursor_override,
            cursor_type=cursor_type,
            effective_grain=effective_grain,
        )
    if spec.start_cursor_override is not None:
        start = spec.start_cursor_override
    start = apply_cursor_replay_policy(
        start=start,
        end=end,
        cursor_start=spec.cursor_start,
        cursor_type=cursor_type,
        lookback=spec.lookback,
        backfill_duration=spec.backfill_duration,
        has_start_override=spec.start_cursor_override is not None,
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
    result = result.replace(MICROBATCH_END_SENTINEL, bounds.end)
    _, has_intrinsics = resolve_cursor_intrinsics(sql=result)
    if (
        has_intrinsics
        or MICROBATCH_START_SENTINEL in result
        or MICROBATCH_END_SENTINEL in result
    ):
        raise ExecutorInputError("executable model SQL contains unresolved cursor markers")
    return result


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


def _is_plain_date(value: object) -> bool:
    """Return whether a value is a date that is not also a datetime."""

    return isinstance(value, date) and not isinstance(value, datetime)


def _floor_date_bound(*, value: date, grain: str) -> date:
    """Floor a plain date bound to the start of its grain."""

    if grain == CursorGrain.MONTH:
        return value.replace(day=1)
    if grain == CursorGrain.YEAR:
        return value.replace(month=1, day=1)
    return value


def _floor_timestamp_bound(*, value: object, grain: str) -> object:
    if _is_plain_date(value):
        return _floor_date_bound(value=cast(date, value), grain=grain)
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
    if _is_plain_date(value):
        return _increment_date_bound(value=cast(date, value), grain=grain)
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


def _increment_date_bound(*, value: date, grain: str) -> date:
    """Step a plain date bound forward by one whole unit of grain."""

    if grain == CursorGrain.MONTH:
        final_month: int = 12
        year: int = value.year + (1 if value.month == final_month else 0)
        month: int = 1 if value.month == final_month else value.month + 1
        return value.replace(year=year, month=month, day=1)
    if grain == CursorGrain.YEAR:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value + timedelta(days=1)


def _normalize_bound(*, value: object, is_end: bool) -> str | None:
    if isinstance(value, datetime):
        normalized: datetime = value + timedelta(seconds=1) if is_end else value
        return normalized.isoformat()
    if _is_plain_date(value):
        plain_date: date = cast(date, value)
        normalized_date: date = plain_date + timedelta(days=1) if is_end else plain_date
        return normalized_date.isoformat()
    if isinstance(value, (int, Decimal)):
        normalized_int: int = int(value) + 1 if is_end else int(value)
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


def _apply_cursor_end_ceiling(
    *,
    current_end: str,
    end_cursor_override: str,
    cursor_type: str | None,
    effective_grain: str | None,
) -> str:
    """Clamp the discovered exclusive end down to the inclusive `--end-cursor-ts` override."""

    if cursor_type == CursorType.TIMESTAMP:
        override_value: date | datetime | None = _parse_timestamp_or_date(end_cursor_override)
        if _try_parse_timestamp(current_end) is None or override_value is None:
            return current_end
        grain: str = effective_grain or CursorGrain.SECOND
        exclusive_override: object = _increment_timestamp_bound(
            value=_floor_timestamp_bound(value=override_value, grain=grain),
            grain=grain,
        )
        normalized_override: str | None = _normalize_bound(value=exclusive_override, is_end=False)
        if normalized_override is None:
            return current_end
        return min(current_end, normalized_override, key=_timestamp_sort_key)
    if cursor_type == CursorType.INTEGER:
        current_integer: int | None = _try_parse_integer(current_end)
        override_integer: int | None = _try_parse_integer(end_cursor_override)
        if current_integer is None or override_integer is None:
            return current_end
        return str(min(current_integer, override_integer + 1))
    return current_end


def _timestamp_sort_key(value: str) -> datetime:
    parsed: datetime | None = _try_parse_timestamp(value)
    if parsed is None:
        return datetime.max
    return parsed


def _parse_timestamp_or_date(value: str) -> date | datetime | None:
    """Parse an override bound as a plain date when date-only, else a datetime."""

    try:
        return date.fromisoformat(value)
    except ValueError:
        return _try_parse_timestamp(value)


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
