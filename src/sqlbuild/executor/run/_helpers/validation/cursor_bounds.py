"""Runtime cursor bound resolution and sentinel substitution."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.cursor_intrinsics import resolve_cursor_intrinsics
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.main.execution.bounded_cursor_override import (
    resolve_bounded_cursor_override,
)
from sqlbuild.compiler.planner.main.execution.cursor_replay_policy import apply_cursor_replay_policy
from sqlbuild.compiler.planner.main.execution.future_cursor_safety import apply_future_cursor_safety
from sqlbuild.compiler.planner.main.execution.maximum_start_safety import apply_maximum_start_policy
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    CursorInputEvidence,
    CursorInputRelation,
    Duration,
    MaximumStartPolicyInputs,
    ModelCursorSnapshot,
    ModelPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    CursorGrain,
    CursorType,
    CursorWatermarkMode,
    MicrobatchStrategy,
)
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run.models import RuntimeCursorSpec
from sqlbuild.executor.run.types import WatermarkResolver
from sqlbuild.spec.contracts.constants import ZERO_DAY_CURSOR_DURATION
from sqlbuild.spec.contracts.models import StartCursorsConfig

_TIMESTAMP_GRAIN_ORDER: dict[str, int] = {
    CursorGrain.SECOND: 0,
    CursorGrain.MINUTE: 1,
    CursorGrain.HOUR: 2,
    CursorGrain.DAY: 3,
    CursorGrain.MONTH: 4,
    CursorGrain.YEAR: 5,
}


def has_runtime_owned_cursor_watermarks(
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> bool:
    """Return whether any cursor input is produced by this invocation."""

    return any(relation.is_runtime_owned for relation in cursor_input_relations)


def has_authoritative_cursor_override(*, entry: ModelPlanEntry) -> bool:
    """Return whether complete operator bounds supersede runtime discovery."""

    return entry.start_cursor_override is not None and entry.end_cursor_override is not None


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
        cursor_end=entry.cursor_end,
        cursor_input_relations=entry.cursor_input_relations,
        cursor_watermark_mode=(
            entry.cursor_watermark_mode
            or (
                CursorWatermarkMode.ALL
                if entry.microbatch_strategy == MicrobatchStrategy.WATERMARK
                else "legacy"
            )
        ),
        microbatch_strategy=entry.microbatch_strategy,
        incremental_strategy=entry.incremental_strategy,
        incremental_mode=entry.incremental_mode,
        start_cursor_override=entry.start_cursor_override,
        end_cursor_override=entry.end_cursor_override,
        lookback=entry.lookback,
        backfill_duration=(
            entry.backfill.duration if entry.backfill.action == BackfillAction.BOUNDED else None
        ),
        read_destination_cursor=read_destination_cursor,
        future_cursor_config=entry.future_cursor_config,
        start_cursor_config=entry.start_cursor_config,
        invocation_time=entry.invocation_time,
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
    on_progress: Callable[[str], None] | None = None,
    watermark_resolver: WatermarkResolver | None = None,
) -> CursorBounds | None:
    """Resolve concrete runtime cursor bounds from target and upstream relations."""

    cursor_type: str | None = spec.cursor_type
    bounded_override: CursorBounds | None = resolve_bounded_cursor_override(
        start_cursor_override=spec.start_cursor_override,
        end_cursor_override=spec.end_cursor_override,
        cursor_type=cursor_type,
        cursor_grain=spec.cursor_grain,
    )
    if bounded_override is not None:
        return bounded_override
    physical_inputs: tuple[tuple[tuple[str, str], tuple[str | None, str | None]], ...] = tuple(
        sorted(
            {
                (cursor_input.relation, cursor_input.cursor_column): (
                    cursor_input.terminal_cursor_start,
                    cursor_input.terminal_cursor_end,
                )
                for cursor_input in spec.cursor_input_relations
            }.items()
        )
    )
    if not physical_inputs:
        return None
    effective_grain: str | None = resolve_effective_timestamp_grain(
        cursor_type=cursor_type,
        downstream_grain=spec.cursor_grain,
        cursor_input_relations=spec.cursor_input_relations,
        microbatch_strategy=spec.microbatch_strategy,
    )

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
    target_eligible_max_raw: object | None = _query_eligible_target_max_raw(
        adapter=adapter,
        connection=connection,
        target_relation=target_relation,
        cursor_column=spec.cursor_column,
        cursor_type=cursor_type,
        cursor_grain=effective_grain,
        target_max_raw=target_max_raw,
        spec=spec,
    )

    read_minimum: bool = target_max_raw is None
    upstream_mins: list[object] = []
    upstream_maxes: list[object] = []
    input_evidence: list[CursorInputEvidence] = []
    input_index: int
    physical_input: tuple[tuple[str, str], tuple[str | None, str | None]]
    for input_index, physical_input in enumerate(physical_inputs, start=1):
        relation_column, terminal_bounds = physical_input
        terminal_start, terminal_end = terminal_bounds
        minimum: object | None
        maximum: object | None
        minimum, maximum = _query_watermark_raw(
            adapter=adapter,
            connection=connection,
            relation=relation_column[0],
            cursor_column=relation_column[1],
            read_minimum=read_minimum,
            query_index=input_index,
            total=len(physical_inputs),
            on_progress=on_progress,
            watermark_resolver=watermark_resolver,
        )
        terminal_maximum: object | None = _terminal_inclusive_maximum(
            value=terminal_end, cursor_type=cursor_type, cursor_grain=effective_grain
        )
        if terminal_maximum is not None:
            maximum = terminal_maximum
        if read_minimum and minimum is None and terminal_start is not None:
            minimum = _raw_terminal_bound(value=terminal_start, cursor_type=cursor_type)
        if maximum is None or (read_minimum and minimum is None):
            if spec.cursor_watermark_mode == CursorWatermarkMode.ALL:
                raise ExecutorInputError(
                    f"required cursor watermark is empty: {relation_column[0]}.{relation_column[1]}"
                )
            continue
        if minimum is not None:
            upstream_mins.append(minimum)
        upstream_maxes.append(maximum)
        normalized_maximum: str | None = _normalize_bound(value=maximum, is_end=False)
        if normalized_maximum is not None:
            input_evidence.append(
                CursorInputEvidence(
                    relation=relation_column[0],
                    cursor_column=relation_column[1],
                    minimum=(
                        _normalize_bound(value=minimum, is_end=False)
                        if minimum is not None
                        else None
                    ),
                    maximum=normalized_maximum,
                )
            )
    if not upstream_maxes:
        return None
    upstream_min_raw: object | None = (
        _minimum_bound_raw(
            values=upstream_mins,
            cursor_type=cursor_type,
            effective_grain=effective_grain,
        )
        if upstream_mins
        else None
    )
    aggregate: Callable[..., object] = (
        _maximum_bound_raw
        if spec.cursor_watermark_mode == CursorWatermarkMode.ANY
        else _minimum_bound_raw
    )
    upstream_max_raw: object = aggregate(
        values=upstream_maxes, cursor_type=cursor_type, effective_grain=effective_grain
    )
    if cursor_type == CursorType.TIMESTAMP and effective_grain is not None:
        start_raw: object | None = (
            target_max_raw if target_max_raw is not None else upstream_min_raw
        )
        if start_raw is None:
            return None
        start: str | None = _normalize_bound(
            value=_floor_timestamp_bound(value=start_raw, grain=effective_grain), is_end=False
        )
        end: str | None = _normalize_bound(
            value=_increment_timestamp_bound(
                value=_floor_timestamp_bound(value=upstream_max_raw, grain=effective_grain),
                grain=effective_grain,
            ),
            is_end=False,
        )
    else:
        start: str | None = (
            _normalize_bound(value=target_max_raw, is_end=False)
            if target_max_raw is not None
            else _normalize_bound(value=upstream_min_raw, is_end=False)
        )
        end: str | None = _normalize_bound(value=upstream_max_raw, is_end=True)
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
    bounds: CursorBounds = apply_maximum_start_policy(
        bounds=CursorBounds(start=start, end=end),
        snapshot=ModelCursorSnapshot(
            target_max=_normalize_bound(value=target_max_raw, is_end=False),
            upstream_mins=_normalize_bounds(
                values=upstream_mins,
                cursor_type=cursor_type,
                effective_grain=effective_grain,
            ),
            upstream_maxes=_normalize_bounds(
                values=upstream_maxes,
                cursor_type=cursor_type,
                effective_grain=effective_grain,
            ),
            physical_target_max=_normalize_bound(value=target_max_raw, is_end=False),
            target_eligible_max=(
                _normalize_effective_timestamp_bound(
                    value=target_eligible_max_raw,
                    cursor_type=cursor_type,
                    effective_grain=effective_grain,
                )
                if target_eligible_max_raw is not None
                else None
            ),
            target_relation=target_relation,
            destination_cursor_column=spec.cursor_column,
        ),
        cursor_type=cursor_type,
        cursor_grain=effective_grain,
        cursor_start=spec.cursor_start,
        lookback=spec.lookback,
        backfill_duration=spec.backfill_duration,
        policy=MaximumStartPolicyInputs(
            config=spec.start_cursor_config,
            invocation_time=spec.invocation_time,
            incremental_strategy=spec.incremental_strategy,
            incremental_mode=spec.incremental_mode,
        ),
        has_start_override=spec.start_cursor_override is not None,
    )
    return _clamp_cursor_end(
        bounds=apply_future_cursor_safety(
            bounds=bounds,
            cursor_type=cursor_type,
            cursor_grain=effective_grain,
            config=spec.future_cursor_config,
            invocation_time=spec.invocation_time,
            has_complete_override=(
                spec.start_cursor_override is not None and spec.end_cursor_override is not None
            ),
            input_evidence=tuple(input_evidence),
        ),
        cursor_end=spec.cursor_end,
        cursor_type=cursor_type,
    )


def _clamp_cursor_end(
    *, bounds: CursorBounds, cursor_end: str | None, cursor_type: str | None
) -> CursorBounds:
    if cursor_end is None:
        return bounds
    end_key: Decimal = _normalized_comparison_key(value=cursor_end, cursor_type=cursor_type)
    if _normalized_comparison_key(value=bounds.start, cursor_type=cursor_type) >= end_key:
        return CursorBounds(start=cursor_end, end=cursor_end)
    if _normalized_comparison_key(value=bounds.end, cursor_type=cursor_type) > end_key:
        return CursorBounds(start=bounds.start, end=cursor_end)
    return bounds


def _normalized_comparison_key(*, value: str, cursor_type: str | None) -> Decimal:
    if cursor_type == CursorType.INTEGER:
        return Decimal(value)
    parsed: datetime = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return Decimal(str(parsed.replace(tzinfo=UTC).timestamp()))


def _normalize_bounds(
    *, values: list[object], cursor_type: str | None, effective_grain: str | None
) -> tuple[str, ...]:
    normalized: list[str] = []
    item: object
    for item in values:
        value: str | None = _normalize_effective_timestamp_bound(
            value=item,
            cursor_type=cursor_type,
            effective_grain=effective_grain,
        )
        if value is not None:
            normalized.append(value)
    return tuple(normalized)


def _normalize_effective_timestamp_bound(
    *, value: object, cursor_type: str | None, effective_grain: str | None
) -> str | None:
    normalized_value: object = value
    if cursor_type == CursorType.TIMESTAMP and effective_grain is not None:
        normalized_value = _floor_timestamp_bound(value=value, grain=effective_grain)
    return _normalize_bound(value=normalized_value, is_end=False)


def _query_watermark_raw(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relation: str,
    cursor_column: str,
    read_minimum: bool,
    query_index: int,
    total: int,
    on_progress: Callable[[str], None] | None,
    watermark_resolver: WatermarkResolver | None,
) -> tuple[object | None, object | None]:
    """Resolve one physical watermark through the optional run-scoped cache."""

    query: Callable[[], tuple[object | None, object | None]] = partial(
        _execute_watermark_query,
        adapter=adapter,
        connection=connection,
        relation=relation,
        cursor_column=cursor_column,
        read_minimum=read_minimum,
        query_index=query_index,
        total=total,
        on_progress=on_progress,
    )
    if watermark_resolver is None:
        return query()
    return watermark_resolver.resolve(
        relation=relation,
        cursor_column=cursor_column,
        read_minimum=read_minimum,
        query=query,
    )


def _execute_watermark_query(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relation: str,
    cursor_column: str,
    read_minimum: bool,
    query_index: int,
    total: int,
    on_progress: Callable[[str], None] | None,
) -> tuple[object | None, object | None]:
    """Execute one optimizer-friendly physical watermark statement."""

    bounds: str = "min,max" if read_minimum else "max"
    identity: str = f"({query_index}/{total}): {relation}.{cursor_column} [{bounds}]"
    select_sql: str = (
        f"MIN({cursor_column}), MAX({cursor_column})" if read_minimum else f"MAX({cursor_column})"
    )
    sql: str = f"SELECT {select_sql} FROM {relation}"
    if on_progress is not None:
        on_progress(f"Inspecting runtime cursor watermark {identity}...")
    query_start: float = time.monotonic()
    try:
        cursor: Any = adapter.execute(connection=connection, sql=sql)
        row: Any = cursor.fetchone()
    except Exception as error:
        elapsed: float = time.monotonic() - query_start
        if on_progress is not None:
            on_progress(f"Failed runtime cursor watermark {identity} ({elapsed:.2f}s): {error}")
        raise
    elapsed = time.monotonic() - query_start
    if on_progress is not None:
        on_progress(f"Inspected runtime cursor watermark {identity} ({elapsed:.2f}s)")
    if row is None:
        return None, None
    if read_minimum:
        return row[0], row[1]
    return None, row[0]


def _minimum_bound_raw(
    *, values: list[object], cursor_type: str | None, effective_grain: str | None
) -> object:
    """Choose a conservative minimum across compatible raw watermark values."""

    if cursor_type != CursorType.TIMESTAMP:
        return min(values)
    grain: str = effective_grain or CursorGrain.SECOND
    return min(values, key=lambda value: _timestamp_comparison_key(value=value, grain=grain))


def _maximum_bound_raw(
    *, values: list[object], cursor_type: str | None, effective_grain: str | None
) -> object:
    """Choose the furthest usable alternative watermark value."""

    if cursor_type != CursorType.TIMESTAMP:
        return max(values)
    grain: str = effective_grain or CursorGrain.SECOND
    return max(values, key=lambda value: _timestamp_comparison_key(value=value, grain=grain))


def _raw_terminal_bound(*, value: str, cursor_type: str | None) -> object:
    if cursor_type == CursorType.INTEGER:
        return Decimal(value)
    return datetime.fromisoformat(value)


def _terminal_inclusive_maximum(
    *, value: str | None, cursor_type: str | None, cursor_grain: str | None
) -> object | None:
    if value is None:
        return None
    if cursor_type == CursorType.INTEGER:
        return Decimal(value) - 1
    duration_by_grain: dict[str, str] = {
        CursorGrain.SECOND: "1s",
        CursorGrain.MINUTE: "1m",
        CursorGrain.HOUR: "1h",
        CursorGrain.DAY: "1d",
        CursorGrain.MONTH: "1mo",
        CursorGrain.YEAR: "1y",
    }
    duration: Duration | None = Duration.parse(
        duration_by_grain.get(cursor_grain or CursorGrain.SECOND, "1s")
    )
    return None if duration is None else duration.subtract_from(datetime.fromisoformat(value))


def _timestamp_comparison_key(*, value: object, grain: str) -> datetime:
    """Normalize DATE and TIMESTAMP values to one grain-aware comparison domain."""

    floored: object = _floor_timestamp_bound(value=value, grain=grain)
    if _is_plain_date(floored):
        return datetime.combine(cast(date, floored), datetime.min.time())
    if isinstance(floored, datetime):
        if floored.tzinfo is not None:
            return floored.astimezone(UTC).replace(tzinfo=None)
        return floored
    raise ExecutorInputError(
        f"runtime timestamp watermark returned incompatible value type '{type(value).__name__}'"
    )


def resolve_effective_timestamp_grain(
    *,
    cursor_type: str | None,
    downstream_grain: str | None,
    cursor_input_relations: tuple[CursorInputRelation, ...],
    microbatch_strategy: str | None = None,
) -> str | None:
    """Return the coarsest timestamp grain participating in runtime-owned replay."""

    if cursor_type != CursorType.TIMESTAMP:
        return None
    if microbatch_strategy == MicrobatchStrategy.WATERMARK:
        return downstream_grain or CursorGrain.SECOND
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
    if has_intrinsics or MICROBATCH_START_SENTINEL in result or MICROBATCH_END_SENTINEL in result:
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


def _query_eligible_target_max_raw(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_relation: str,
    cursor_column: str,
    cursor_type: str | None,
    cursor_grain: str | None,
    target_max_raw: object | None,
    spec: RuntimeCursorSpec,
) -> object | None:
    """Read the target MAX at or below the automatic-start horizon when recovery is needed."""

    config: StartCursorsConfig | None = spec.start_cursor_config
    target_max: str | None = _normalize_bound(value=target_max_raw, is_end=False)
    if (
        config is None
        or config.max_ahead is None
        or cursor_type != CursorType.TIMESTAMP
        or spec.invocation_time is None
        or target_max is None
        or spec.start_cursor_override is not None
    ):
        return None
    horizon: str = _maximum_allowed_start(
        discovered_value=target_max,
        cursor_grain=cursor_grain,
        invocation_time=spec.invocation_time,
        max_ahead=config.max_ahead,
    )
    if datetime.fromisoformat(target_max) <= datetime.fromisoformat(horizon):
        return None
    eligible_sql: str = adapter.render_max_cursor_at_or_before(
        relation=target_relation,
        cursor_column=cursor_column,
        maximum_allowed=horizon,
        cursor_type=cursor_type,
        is_date=_is_plain_date(target_max_raw),
    )
    cursor: Any = adapter.execute(
        connection=connection,
        sql=eligible_sql,
    )
    row: Any = cursor.fetchone()
    return None if row is None else row[0]


def _maximum_allowed_start(
    *, discovered_value: str, cursor_grain: str | None, invocation_time: datetime, max_ahead: str
) -> str:
    duration: Duration | None = Duration.parse(max_ahead)
    if duration is None and max_ahead == ZERO_DAY_CURSOR_DURATION:
        duration = Duration()
    if duration is None:
        raise ExecutorInputError(f"invalid cursors.start.max_ahead '{max_ahead}'")
    maximum: datetime = duration.add_to(invocation_time.astimezone(UTC).replace(tzinfo=None))
    floored: object = _floor_timestamp_bound(
        value=maximum, grain=cursor_grain or CursorGrain.SECOND
    )
    if not isinstance(floored, datetime):
        raise ExecutorInputError("maximum automatic start could not be normalized")
    if _is_plain_date_string(discovered_value):
        return floored.date().isoformat()
    parsed: datetime = datetime.fromisoformat(discovered_value)
    return (
        floored.replace(tzinfo=UTC).isoformat()
        if parsed.tzinfo is not None
        else floored.isoformat()
    )


def _is_plain_date_string(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


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
