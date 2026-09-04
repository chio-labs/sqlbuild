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
from sqlbuild.compiler.planner.main.execution.inclusive_cursor_end import (
    _advance_discovered_cursor_end as advance_discovered_cursor_end,
)
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
from sqlbuild.cursor_algebra.constants import GRAIN_ORDER
from sqlbuild.cursor_algebra.main.clamp import clamp
from sqlbuild.cursor_algebra.main.compare import compare
from sqlbuild.cursor_algebra.main.exclusive_to_inclusive import exclusive_to_inclusive
from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain
from sqlbuild.cursor_algebra.main.inclusive_to_exclusive import inclusive_to_exclusive
from sqlbuild.cursor_algebra.main.max_bound import max_bound
from sqlbuild.cursor_algebra.main.min_bound import min_bound
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.sentinel_from_token import sentinel_from_token
from sqlbuild.cursor_algebra.main.sentinel_to_token import sentinel_to_token
from sqlbuild.cursor_algebra.main.try_parse import try_parse
from sqlbuild.cursor_algebra.models import (
    AlignedInterval,
    DateValue,
    IntegerValue,
    TimestampValue,
)
from sqlbuild.cursor_algebra.types import BoundSentinel, CursorScalar
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run.models import RuntimeCursorInputRelation, RuntimeCursorSpec
from sqlbuild.executor.run.types import WatermarkResolver
from sqlbuild.spec.contracts.constants import ZERO_DAY_CURSOR_DURATION
from sqlbuild.spec.contracts.models import StartCursorsConfig


def has_runtime_owned_cursor_watermarks(
    cursor_input_relations: tuple[CursorInputRelation | RuntimeCursorInputRelation, ...],
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
        cursor_input_relations=tuple(
            RuntimeCursorInputRelation(
                relation=relation.relation,
                cursor_column=relation.cursor_column,
                cursor_grain=(
                    relation.cursor_grain.value if relation.cursor_grain is not None else None
                ),
                is_model_backed=relation.is_model_backed,
                is_runtime_produced=relation.is_runtime_produced,
                terminal_cursor_start=(
                    render(value=relation.terminal_cursor_start)
                    if relation.terminal_cursor_start is not None
                    else None
                ),
                terminal_cursor_end=(
                    render(value=relation.terminal_cursor_end)
                    if relation.terminal_cursor_end is not None
                    else None
                ),
            )
            for relation in entry.cursor_input_relations
        ),
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
    physical_inputs: tuple[tuple[tuple[str, str], RuntimeCursorInputRelation], ...] = tuple(
        sorted(
            {
                (cursor_input.relation, cursor_input.cursor_column): cursor_input
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
    discovered_grain: str | None = (
        effective_grain
        if spec.cursor_grain is not None
        or any(item.cursor_grain is not None for item in spec.cursor_input_relations)
        else None
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
    upstream_availability_ends: list[object] = []
    input_evidence: list[CursorInputEvidence] = []
    input_index: int
    physical_input: tuple[tuple[str, str], RuntimeCursorInputRelation]
    for input_index, physical_input in enumerate(physical_inputs, start=1):
        relation_column, cursor_input = physical_input
        terminal_start: str | None = cursor_input.terminal_cursor_start
        terminal_end: str | None = cursor_input.terminal_cursor_end
        input_grain: str | None = cursor_input.cursor_grain or discovered_grain
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
            value=terminal_end, cursor_type=cursor_type, cursor_grain=input_grain
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
        if (
            cursor_type == CursorType.TIMESTAMP
            and spec.microbatch_strategy == MicrobatchStrategy.WATERMARK
        ):
            availability_end: object = (
                _raw_terminal_bound(value=terminal_end, cursor_type=cursor_type)
                if terminal_end is not None
                else advance_discovered_cursor_end(
                    value=maximum,
                    cursor_type=cursor_type,
                    cursor_grain=input_grain,
                )
            )
            upstream_availability_ends.append(availability_end)
        normalized_maximum: str | None = _normalize_bound(value=maximum, is_end=False)
        if normalized_maximum is not None:
            input_evidence.append(
                CursorInputEvidence(
                    relation=relation_column[0],
                    cursor_column=relation_column[1],
                    minimum=(
                        parse(
                            raw=_normalize_bound(value=minimum, is_end=False),
                            cursor_type=cursor_type or CursorType.TIMESTAMP,
                        )
                        if minimum is not None
                        else None
                    ),
                    maximum=parse(
                        raw=normalized_maximum,
                        cursor_type=cursor_type or CursorType.TIMESTAMP,
                    ),
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
    watermark_timestamp: bool = (
        cursor_type == CursorType.TIMESTAMP
        and spec.microbatch_strategy == MicrobatchStrategy.WATERMARK
    )
    upstream_max_raw: object = aggregate(
        values=(upstream_availability_ends if watermark_timestamp else upstream_maxes),
        cursor_type=cursor_type,
        effective_grain=(CursorGrain.SECOND if watermark_timestamp else effective_grain),
    )
    if cursor_type == CursorType.TIMESTAMP and effective_grain is not None:
        start_raw: object | None = (
            target_max_raw if target_max_raw is not None else upstream_min_raw
        )
        if start_raw is None:
            return None
        start: str | None = _normalize_bound(
            value=_normalize_raw_temporal_grain(value=start_raw, grain=effective_grain),
            is_end=False,
        )
        end: str | None = _normalize_bound(
            value=(
                _normalize_raw_temporal_grain(value=upstream_max_raw, grain=effective_grain)
                if watermark_timestamp and discovered_grain is not None
                else upstream_max_raw
                if watermark_timestamp
                else advance_discovered_cursor_end(
                    value=upstream_max_raw,
                    cursor_type=cursor_type,
                    cursor_grain=discovered_grain,
                )
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
            target_max=_parse_optional_normalized(
                value=_normalize_bound(value=target_max_raw, is_end=False),
                cursor_type=cursor_type,
            ),
            upstream_mins=tuple(
                parse(raw=value, cursor_type=cursor_type or CursorType.TIMESTAMP)
                for value in _normalize_bounds(
                    values=upstream_mins,
                    cursor_type=cursor_type,
                    effective_grain=effective_grain,
                )
            ),
            upstream_maxes=tuple(
                parse(raw=value, cursor_type=cursor_type or CursorType.TIMESTAMP)
                for value in _normalize_bounds(
                    values=upstream_maxes,
                    cursor_type=cursor_type,
                    effective_grain=effective_grain,
                )
            ),
            physical_target_max=_parse_optional_normalized(
                value=_normalize_bound(value=target_max_raw, is_end=False),
                cursor_type=cursor_type,
            ),
            target_eligible_max=(
                _parse_optional_normalized(
                    value=_normalize_effective_timestamp_bound(
                        value=target_eligible_max_raw,
                        cursor_type=cursor_type,
                        effective_grain=effective_grain,
                    ),
                    cursor_type=cursor_type,
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
    effective_type: str = cursor_type or CursorType.TIMESTAMP
    end_value: CursorScalar = parse(raw=cursor_end, cursor_type=effective_type)
    if isinstance(bounds.start, BoundSentinel) or isinstance(bounds.end, BoundSentinel):
        return bounds
    if compare(left=bounds.start, right=end_value) >= 0:
        return CursorBounds(start=cursor_end, end=cursor_end)
    if compare(left=bounds.end, right=end_value) > 0:
        if effective_type == CursorType.INTEGER:
            start_value: CursorScalar = bounds.start
            current_end_value: CursorScalar = bounds.end
            if (
                isinstance(start_value, IntegerValue)
                and isinstance(current_end_value, IntegerValue)
                and isinstance(end_value, IntegerValue)
            ):
                original: AlignedInterval = AlignedInterval(
                    start=start_value, end=current_end_value, grain=None
                )
                ceiling: AlignedInterval = AlignedInterval(
                    start=start_value, end=end_value, grain=None
                )
                clamped: AlignedInterval | None = clamp(interval=original, bounds=ceiling)
                if clamped is not None:
                    return CursorBounds(start=bounds.start, end=cursor_end)
        return CursorBounds(start=bounds.start, end=cursor_end)
    return bounds


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


def _parse_optional_normalized(
    *, value: str | None, cursor_type: str | None
) -> CursorScalar | None:
    if value is None:
        return None
    return parse(raw=value, cursor_type=cursor_type or CursorType.TIMESTAMP)


def _normalize_effective_timestamp_bound(
    *, value: object, cursor_type: str | None, effective_grain: str | None
) -> str | None:
    normalized_value: object = value
    if cursor_type == CursorType.TIMESTAMP and effective_grain is not None:
        normalized_value = _normalize_raw_temporal_grain(value=value, grain=effective_grain)
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

    if cursor_type == CursorType.TIMESTAMP:
        grain: str = effective_grain or CursorGrain.SECOND
        normalized: list[object] = [
            _normalize_raw_temporal_grain(value=value, grain=grain) for value in values
        ]
        try:
            selected: object = min_bound(values=normalized, cursor_type=cursor_type)
        except ValueError as error:
            raise ExecutorInputError(
                "runtime timestamp watermark returned incompatible value type"
            ) from error
        return values[normalized.index(selected)]
    if cursor_type == CursorType.INTEGER:
        return min_bound(values=values, cursor_type=cursor_type)
    return min(values)


def _maximum_bound_raw(
    *, values: list[object], cursor_type: str | None, effective_grain: str | None
) -> object:
    """Choose the furthest usable alternative watermark value."""

    if cursor_type == CursorType.TIMESTAMP:
        grain: str = effective_grain or CursorGrain.SECOND
        normalized: list[object] = [
            _normalize_raw_temporal_grain(value=value, grain=grain) for value in values
        ]
        try:
            selected: object = max_bound(values=normalized, cursor_type=cursor_type)
        except ValueError as error:
            raise ExecutorInputError(
                "runtime timestamp watermark returned incompatible value type"
            ) from error
        return values[normalized.index(selected)]
    if cursor_type == CursorType.INTEGER:
        return max_bound(values=values, cursor_type=cursor_type)
    return max(values)


def _raw_terminal_bound(*, value: str, cursor_type: str | None) -> object:
    if cursor_type == CursorType.INTEGER:
        return parse(raw=value, cursor_type=CursorType.INTEGER).value
    return datetime.fromisoformat(value)


def _terminal_inclusive_maximum(
    *, value: str | None, cursor_type: str | None, cursor_grain: str | None
) -> object | None:
    if value is None:
        return None
    if cursor_type == CursorType.INTEGER:
        return exclusive_to_inclusive(
            value=parse(raw=value, cursor_type=CursorType.INTEGER), grain=None
        ).value
    parsed: CursorScalar | None = try_parse(raw=value, cursor_type=CursorType.TIMESTAMP)
    if parsed is None:
        return None
    if isinstance(parsed, DateValue):
        parsed = TimestampValue(value=datetime.combine(parsed.value, datetime.min.time()))
    inclusive: CursorScalar = exclusive_to_inclusive(
        value=parsed, grain=CursorGrain(cursor_grain or CursorGrain.SECOND)
    )
    return inclusive.value


def resolve_effective_timestamp_grain(
    *,
    cursor_type: str | None,
    downstream_grain: str | None,
    cursor_input_relations: tuple[CursorInputRelation | RuntimeCursorInputRelation, ...],
    microbatch_strategy: str | None = None,
) -> str | None:
    """Return the coarsest timestamp grain participating in runtime-owned replay."""

    if cursor_type != CursorType.TIMESTAMP:
        return None
    if microbatch_strategy == MicrobatchStrategy.WATERMARK:
        return downstream_grain or CursorGrain.SECOND
    effective: str = downstream_grain or CursorGrain.SECOND
    cursor_input: CursorInputRelation | RuntimeCursorInputRelation
    for cursor_input in cursor_input_relations:
        input_grain: str = cursor_input.cursor_grain or CursorGrain.SECOND
        if GRAIN_ORDER[CursorGrain(input_grain)] > GRAIN_ORDER[CursorGrain(effective)]:
            effective = input_grain
    return effective


def substitute_cursor_sentinels(*, sql: str, bounds: CursorBounds) -> str:
    """Substitute runtime cursor sentinels with concrete bounds."""

    if sentinel_from_token(token=MICROBATCH_START_SENTINEL) is None:
        raise ExecutorInputError("invalid start cursor marker")
    result: str = sql.replace(MICROBATCH_START_SENTINEL, sentinel_to_token(sentinel=bounds.start))
    result = result.replace(MICROBATCH_END_SENTINEL, sentinel_to_token(sentinel=bounds.end))
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
    floored: object = _normalize_raw_temporal_grain(
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


def _normalize_raw_temporal_grain(*, value: object, grain: str) -> object:
    parsed: CursorScalar | None = try_parse(raw=value, cursor_type=CursorType.TIMESTAMP)
    if parsed is None:
        return value
    return floor_to_grain(value=parsed, grain=CursorGrain(grain)).value


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


def _apply_cursor_end_ceiling(
    *,
    current_end: str,
    end_cursor_override: str,
    cursor_type: str | None,
    effective_grain: str | None,
) -> str:
    """Clamp the discovered exclusive end down to the inclusive `--end-cursor-ts` override."""

    if cursor_type == CursorType.TIMESTAMP:
        current_value: CursorScalar | None = try_parse(
            raw=current_end, cursor_type=CursorType.TIMESTAMP
        )
        override_value: CursorScalar | None = try_parse(
            raw=end_cursor_override, cursor_type=CursorType.TIMESTAMP
        )
        if current_value is None or override_value is None:
            return current_end
        grain: CursorGrain = CursorGrain(effective_grain or CursorGrain.SECOND)
        exclusive_override: CursorScalar = inclusive_to_exclusive(
            value=floor_to_grain(value=override_value, grain=grain), grain=grain
        )
        return render(
            value=min_bound(
                values=(current_value, exclusive_override), cursor_type=CursorType.TIMESTAMP
            )
        )
    if cursor_type == CursorType.INTEGER:
        current_integer: CursorScalar | None = try_parse(
            raw=current_end, cursor_type=CursorType.INTEGER
        )
        override_integer: CursorScalar | None = try_parse(
            raw=end_cursor_override, cursor_type=CursorType.INTEGER
        )
        if not isinstance(current_integer, IntegerValue) or not isinstance(
            override_integer, IntegerValue
        ):
            return current_end
        return render(
            value=min_bound(
                values=(
                    current_integer,
                    inclusive_to_exclusive(value=override_integer, grain=None),
                ),
                cursor_type=CursorType.INTEGER,
            )
        )
    return current_end
