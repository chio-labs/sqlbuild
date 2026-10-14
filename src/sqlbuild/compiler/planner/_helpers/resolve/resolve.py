"""Cursor-bound computation and native per-model SQL resolution."""

from __future__ import annotations

from datetime import datetime

from sqlbuild._native import (
    get_config_cursor_bound,
    get_config_str,
    resolve_bounded_cursor_override,
    resolve_cursor_input_roles,
)
from sqlbuild._native import resolve_function_sql as resolve_function_sql
from sqlbuild._native import resolve_model_hook_entries as resolve_model_hook_entries
from sqlbuild._native import resolve_model_sql as resolve_model_sql
from sqlbuild.adapter.contract.models import RelationInfo, RelationLookup
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    compute_cursor_bounds,
    cursor_inputs_without_rows,
    empty_cursor_window,
    empty_input_rebuild_refusal,
    unreadable_cursor_inputs_error,
    without_destination_cursor,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor_policies import (
    resolve_future_cursor_config,
    resolve_start_cursor_config,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.execution.future_cursor_safety import apply_future_cursor_safety
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorBounds,
    MaximumStartPolicyInputs,
    ModelCursorSnapshot,
    ModelPlanContext,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, IncrementalMode, MaterializationType
from sqlbuild.cursor_algebra.types import BoundSentinel
from sqlbuild.spec.contracts.models import FutureCursorsConfig, StartCursorsConfig


def _compute_model_cursor_bounds(
    *,
    model: CompiledModelView,
    snapshot: WarehouseSnapshot,
    backfill: BackfillResult,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    runtime_cursor_producer_names: frozenset[str],
    context: ModelPlanContext,
    replaces_relation: bool = False,
) -> CursorBounds | None:
    """Compute cursor bounds for a model if it is incremental with a cursor."""

    materialized: str | None = get_config_str(values=model.config.values, key="materialized")
    cursor_column: str | None = get_config_str(values=model.config.values, key="cursor")

    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None

    incremental_mode: str | None = get_config_str(
        values=model.config.values, key="incremental_mode"
    )
    future_cursor_config: FutureCursorsConfig | None = resolve_future_cursor_config(
        model=model, project_config=context.future_cursor_config
    )
    start_cursor_config: StartCursorsConfig | None = resolve_start_cursor_config(
        model=model, project_config=context.start_cursor_config
    )
    invocation_time: datetime | None = context.invocation_time
    is_microbatch: bool = incremental_mode == IncrementalMode.MICROBATCH
    if is_microbatch:
        return CursorBounds(start=BoundSentinel.START, end=BoundSentinel.END)

    bounded_override: CursorBounds | None = resolve_bounded_cursor_override(
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
        cursor_grain=get_config_str(values=model.config.values, key="cursor_grain"),
    )
    if bounded_override is not None:
        return bounded_override

    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    runtime_owned: bool = bool(
        set(resolve_cursor_input_roles(model=model).watermark_inputs)
        & runtime_cursor_producer_names
    )
    if not full_refresh and not runtime_owned and cursor_snapshot is not None:
        empty_inputs: tuple[str, ...] = cursor_inputs_without_rows(
            cursor_snapshot=cursor_snapshot
        ).input_names
        if (
            empty_inputs
            and replaces_relation
            and (
                _destination_exists(model=model, snapshot=snapshot)
                or _history_redirected(model=model, cursor_snapshot=cursor_snapshot)
            )
        ):
            message, help_text = empty_input_rebuild_refusal(
                model_name=model.name,
                input_names=empty_inputs,
                cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
            )
            raise PlannerInputError(message, code="S302", help=help_text)
        if empty_inputs:
            return empty_cursor_window(
                cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
                cursor_start=get_config_cursor_bound(
                    values=model.config.values, key="cursor_start"
                ),
            )
        if not cursor_snapshot.watermarks_available:
            raise unreadable_cursor_inputs_error(
                model_name=model.name,
                cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
                input_names=(
                    cursor_snapshot.unreadable_input_names
                    or cursor_snapshot.unavailable_watermark_tags
                ),
            )

    if full_refresh:
        return None

    if runtime_owned:
        return CursorBounds(start=BoundSentinel.START, end=BoundSentinel.END)
    if cursor_snapshot is None:
        return None
    if replaces_relation:
        cursor_snapshot = without_destination_cursor(cursor_snapshot=cursor_snapshot)

    lookback: str | None = get_config_str(values=model.config.values, key="lookback")
    cursor_start: str | None = get_config_cursor_bound(
        values=model.config.values, key="cursor_start"
    )
    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=is_microbatch,
        cursor_grain=get_config_str(values=model.config.values, key="cursor_grain"),
        maximum_start_policy=MaximumStartPolicyInputs(
            config=start_cursor_config,
            invocation_time=invocation_time,
            incremental_strategy=get_config_str(
                values=model.config.values, key="incremental_strategy"
            ),
            incremental_mode=incremental_mode,
        ),
    )
    if bounds is None:
        return None
    return apply_future_cursor_safety(
        bounds=bounds,
        cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
        cursor_grain=get_config_str(values=model.config.values, key="cursor_grain"),
        config=future_cursor_config,
        invocation_time=invocation_time,
        has_complete_override=(
            start_cursor_override is not None and end_cursor_override is not None
        ),
        input_evidence=cursor_snapshot.input_evidence,
    )


def _destination_exists(*, model: CompiledModelView, snapshot: WarehouseSnapshot) -> bool:
    """Return whether the model's resolved destination, alias included, exists in full identity."""

    relation: RelationInfo | None = snapshot.existing_relations.get(model.name)
    return relation is not None and relation.identity == RelationLookup.key(
        database=model.destination.database,
        schema=model.destination.schema,
        name=model.destination.name,
    )


def _history_redirected(*, model: CompiledModelView, cursor_snapshot: ModelCursorSnapshot) -> bool:
    """Return whether the model's cursor history lives in a relation other than its destination."""

    return (
        cursor_snapshot.target_relation is not None
        and cursor_snapshot.target_relation != model.destination.qualified_name
    )
