"""Per-model SQL resolution orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.main._cursor_roles import resolve_cursor_input_roles
from sqlbuild.compiler.compile.main.cursor_intrinsics import resolve_cursor_intrinsics
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledRelationLocation,
    CursorInputRoles,
)
from sqlbuild.compiler.discovery.models import SqlHookEntry
from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    resolve_bounded_cursor_override,
)
from sqlbuild.compiler.planner._helpers.resolve.config import (
    get_config_append_cursor_inclusive,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    compute_cursor_bounds,
    without_destination_cursor,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor_intrinsics import (
    render_cursor_intrinsic_bounds,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor_policies import (
    resolve_future_cursor_config,
    resolve_start_cursor_config,
)
from sqlbuild.compiler.planner._helpers.resolve.refs import (
    resolve_dbt_ref_references,
    resolve_ref_references,
    resolve_table_function_references,
    resolve_udf_references,
)
from sqlbuild.compiler.planner._helpers.resolve.sources import (
    resolve_source_references,
)
from sqlbuild.compiler.planner.constants import (
    MODEL_POST_HOOKS_CONFIG_KEY,
    MODEL_PRE_HOOKS_CONFIG_KEY,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.execution.future_cursor_safety import apply_future_cursor_safety
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorBounds,
    CursorOverridePair,
    MaximumStartPolicyInputs,
    ModelCursorSnapshot,
    ModelPlanContext,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, IncrementalMode, MaterializationType
from sqlbuild.compiler.references.main.assert_no_unresolved_sql_markers import (
    assert_no_unresolved_sql_markers,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.cursor_algebra.types import BoundSentinel
from sqlbuild.spec.contracts.main.get_config_cursor_bound import get_config_cursor_bound
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import FutureCursorsConfig, SourceEntry, StartCursorsConfig


def resolve_model_sql(
    *,
    adapter: BaseAdapter,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    context: ModelPlanContext,
    backfill: BackfillResult,
    full_refresh: bool,
    cursor_overrides: CursorOverridePair,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    replaces_relation: bool = False,
    full_rebuild_cause: str | None = None,
) -> str:
    """Resolve all references in a model's query SQL to produce executable SQL."""

    model_locations: dict[str, CompiledRelationLocation] = context.model_locations
    seed_locations: dict[str, CompiledRelationLocation] = context.seed_locations
    function_locations: dict[str, CompiledRelationLocation] = context.function_locations
    source_map: dict[str, SourceEntry] = context.source_map
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = context.source_warehouse_columns
    star_exclude_keyword: str = context.star_exclude_keyword
    query_sql: str = model.query_sql
    cursor_type: str | None = get_config_str(values=model.config.values, key="cursor_type")

    cursor_bounds: CursorBounds | None = _compute_model_cursor_bounds(
        model=model,
        snapshot=snapshot,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=cursor_overrides.start_cursor_override,
        end_cursor_override=cursor_overrides.end_cursor_override,
        runtime_cursor_producer_names=context.runtime_cursor_producer_names,
        context=context,
        replaces_relation=replaces_relation,
    )

    cursor_roles: CursorInputRoles = resolve_cursor_input_roles(model=model)
    lower_bound_inclusive: bool = get_config_append_cursor_inclusive(model)

    query_sql = resolve_source_references(
        query_sql=query_sql,
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
        star_exclude_keyword=star_exclude_keyword,
        cursor_bounds=cursor_bounds,
        cursor_filter_inputs=cursor_roles.filter_inputs,
        adapter=adapter,
        cursor_type=cursor_type,
        lower_bound_inclusive=lower_bound_inclusive,
    )

    query_sql = resolve_ref_references(
        query_sql=query_sql,
        model_locations=model_locations,
        seed_locations=seed_locations,
        cursor_bounds=cursor_bounds,
        cursor_filter_inputs=cursor_roles.filter_inputs,
        adapter=adapter,
        cursor_type=cursor_type,
        lower_bound_inclusive=lower_bound_inclusive,
    )

    query_sql = resolve_dbt_ref_references(
        query_sql=query_sql,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    query_sql = resolve_udf_references(
        query_sql=query_sql,
        function_locations=function_locations or {},
        adapter=adapter,
    )
    query_sql = resolve_table_function_references(
        query_sql=query_sql,
        function_locations=function_locations or {},
        adapter=adapter,
    )
    _, has_intrinsics = resolve_cursor_intrinsics(sql=query_sql)
    if has_intrinsics:
        if cursor_bounds is None:
            raise _unresolved_cursor_bounds_error(
                model_name=model.name,
                full_rebuild_cause=full_rebuild_cause
                or ("--full-refresh" if full_refresh else None),
            )
        query_sql = render_cursor_intrinsic_bounds(
            sql=query_sql, bounds=cursor_bounds, cursor_type=cursor_type, adapter=adapter
        )

    assert_no_unresolved_sql_markers(sql=query_sql, context=f"Model '{model.name}' planned SQL")
    return query_sql


def _unresolved_cursor_bounds_error(
    *, model_name: str, full_rebuild_cause: str | None
) -> PlannerInputError:
    if full_rebuild_cause is None:
        return PlannerInputError(
            f"Model '{model_name}' uses cursor intrinsics, but cursor bounds could not be resolved"
        )
    return PlannerInputError(
        f"Model '{model_name}' was given a FULL backfill ({full_rebuild_cause}), but it uses "
        "cursor intrinsics and a non-microbatch full rebuild has no cursor interval",
        help=(
            "rebuild it with an explicit cursor interval (--start-cursor-ts and "
            "--end-cursor-ts, or the -int forms), or make it a microbatch model so a full "
            "rebuild can run batch by batch"
        ),
    )


def resolve_function_sql(
    *,
    adapter: BaseAdapter,
    function: CompiledFunction,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    function_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
) -> str:
    """Resolve relation and function references in a SQL function body."""

    return _resolve_unbounded_sql(
        sql=function.body_sql,
        context=ModelPlanContext(
            model_locations=model_locations,
            models_by_name={},
            seed_locations=seed_locations,
            function_locations=function_locations,
            source_map=source_map,
            source_warehouse_columns=source_warehouse_columns,
            star_exclude_keyword=star_exclude_keyword,
        ),
        adapter=adapter,
        external_sql_reference_resolver=None,
        label=f"Function '{function.name}'",
    )


def _compute_model_cursor_bounds(
    *,
    model: CompiledModel,
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
    if (
        not full_refresh
        and not runtime_owned
        and cursor_snapshot is not None
        and not cursor_snapshot.watermarks_available
    ):
        unavailable: str = ", ".join(cursor_snapshot.unavailable_watermark_tags)
        raise PlannerInputError(
            f"model '{model.name}': required cursor watermark bounds are unavailable: "
            f"{unavailable}",
            code="S302",
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


def resolve_model_hook_entries(
    *,
    model: CompiledModel,
    adapter: BaseAdapter,
    context: ModelPlanContext,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> tuple[object, object]:
    """Return the model's pre and post hooks with SQL hook references resolved like model SQL."""

    pre_hooks, post_hooks = (
        _resolve_hook_value(
            value=model.config.values.get(hook_key),
            label=f"Model '{model.name}' {hook_key}",
            adapter=adapter,
            context=context,
            external_sql_reference_resolver=external_sql_reference_resolver,
        )
        for hook_key in (MODEL_PRE_HOOKS_CONFIG_KEY, MODEL_POST_HOOKS_CONFIG_KEY)
    )
    return pre_hooks, post_hooks


def _resolve_hook_value(
    *,
    value: object,
    label: str,
    adapter: BaseAdapter,
    context: ModelPlanContext,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> object:
    if isinstance(value, SqlHookEntry):
        return replace(
            value,
            statement=_resolve_unbounded_sql(
                sql=value.statement,
                label=label,
                adapter=adapter,
                context=context,
                external_sql_reference_resolver=external_sql_reference_resolver,
            ),
        )
    if isinstance(value, list | tuple):
        resolved: list[object] = [
            _resolve_hook_value(
                value=item,
                label=f"{label}[{index}]",
                adapter=adapter,
                context=context,
                external_sql_reference_resolver=external_sql_reference_resolver,
            )
            for index, item in enumerate(value)
        ]
        return resolved if isinstance(value, list) else tuple(resolved)
    return value


def _resolve_unbounded_sql(
    *,
    sql: str,
    label: str,
    adapter: BaseAdapter,
    context: ModelPlanContext,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> str:
    resolved: str = resolve_source_references(
        query_sql=sql,
        source_map=context.source_map,
        source_warehouse_columns=context.source_warehouse_columns,
        star_exclude_keyword=context.star_exclude_keyword,
        cursor_bounds=None,
        cursor_filter_inputs={},
        adapter=adapter,
        cursor_type=None,
        lower_bound_inclusive=True,
    )
    resolved = resolve_ref_references(
        query_sql=resolved,
        model_locations=context.model_locations,
        seed_locations=context.seed_locations,
        cursor_bounds=None,
        cursor_filter_inputs={},
        adapter=adapter,
        cursor_type=None,
        lower_bound_inclusive=True,
    )
    resolved = resolve_dbt_ref_references(
        query_sql=resolved, external_sql_reference_resolver=external_sql_reference_resolver
    )
    resolved = resolve_udf_references(
        query_sql=resolved, function_locations=context.function_locations or {}, adapter=adapter
    )
    resolved = resolve_table_function_references(
        query_sql=resolved, function_locations=context.function_locations or {}, adapter=adapter
    )
    assert_no_unresolved_sql_markers(sql=resolved, context=f"{label} planned SQL")
    return resolved
