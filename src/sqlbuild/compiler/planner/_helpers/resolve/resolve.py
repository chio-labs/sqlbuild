"""Per-model SQL resolution orchestration."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.main.cursor_intrinsics import resolve_cursor_intrinsics
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledRelationLocation,
)
from sqlbuild.compiler.planner._helpers.resolve.config import (
    get_config_append_cursor_inclusive,
    get_config_cursor_start,
    get_config_str,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor import compute_cursor_bounds
from sqlbuild.compiler.planner._helpers.resolve.cursor_inputs import (
    has_model_backed_cursor_inputs,
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
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorBounds,
    CursorOverridePair,
    ModelCursorSnapshot,
    ModelPlanContext,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, IncrementalMode, MaterializationType
from sqlbuild.compiler.references.main.assert_no_unresolved_sql_markers import (
    assert_no_unresolved_sql_markers,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.spec.contracts.models import SourceEntry


def resolve_model_sql(
    *,
    adapter: BaseAdapter,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    context: ModelPlanContext,
    backfill: BackfillResult,
    full_refresh: bool,
    cursor_overrides: CursorOverridePair,
    suppress_runtime_cursor_bounds: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> str:
    """Resolve all references in a model's query SQL to produce executable SQL."""

    model_locations: dict[str, CompiledRelationLocation] = context.model_locations
    seed_locations: dict[str, CompiledRelationLocation] = context.seed_locations
    function_locations: dict[str, CompiledRelationLocation] = context.function_locations
    source_map: dict[str, SourceEntry] = context.source_map
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = context.source_warehouse_columns
    star_exclude_keyword: str = context.star_exclude_keyword
    query_sql: str = model.query_sql
    cursor_type: str | None = get_config_str(model=model, key="cursor_type")

    cursor_bounds: CursorBounds | None = _compute_model_cursor_bounds(
        model=model,
        snapshot=snapshot,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=cursor_overrides.start_cursor_override,
        end_cursor_override=cursor_overrides.end_cursor_override,
        model_locations=model_locations,
        seed_locations=seed_locations,
        suppress_runtime_cursor_bounds=suppress_runtime_cursor_bounds,
    )

    cursor_inputs: dict[str, str] = _get_cursor_inputs(model)
    lower_bound_inclusive: bool = get_config_append_cursor_inclusive(model)

    query_sql = resolve_source_references(
        query_sql=query_sql,
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
        star_exclude_keyword=star_exclude_keyword,
        cursor_bounds=cursor_bounds,
        cursor_inputs=cursor_inputs,
        adapter=adapter,
        cursor_type=cursor_type,
        lower_bound_inclusive=lower_bound_inclusive,
    )

    query_sql = resolve_ref_references(
        query_sql=query_sql,
        model_locations=model_locations,
        seed_locations=seed_locations,
        cursor_bounds=cursor_bounds,
        cursor_inputs=cursor_inputs,
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
            if full_refresh:
                raise PlannerInputError(
                    f"Model '{model.name}' uses cursor intrinsics, but non-microbatch full "
                    "refresh has no cursor interval"
                )
            raise PlannerInputError(
                f"Model '{model.name}' uses cursor intrinsics, but cursor bounds could not be "
                "resolved"
            )
        query_sql, _ = resolve_cursor_intrinsics(
            sql=query_sql,
            start_sql=adapter.render_cursor_bound_literal(
                value=cursor_bounds.start,
                cursor_type=cursor_type,
            ),
            end_sql=adapter.render_cursor_bound_literal(
                value=cursor_bounds.end,
                cursor_type=cursor_type,
            ),
        )

    assert_no_unresolved_sql_markers(sql=query_sql, context=f"Model '{model.name}' planned SQL")
    return query_sql


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

    query_sql: str = resolve_source_references(
        query_sql=function.body_sql,
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
        star_exclude_keyword=star_exclude_keyword,
        cursor_bounds=None,
        cursor_inputs={},
        adapter=adapter,
        cursor_type=None,
        lower_bound_inclusive=True,
    )
    query_sql = resolve_ref_references(
        query_sql=query_sql,
        model_locations=model_locations,
        seed_locations=seed_locations,
        cursor_bounds=None,
        cursor_inputs={},
        adapter=adapter,
        cursor_type=None,
        lower_bound_inclusive=True,
    )
    query_sql = resolve_dbt_ref_references(query_sql=query_sql)
    query_sql = resolve_udf_references(
        query_sql=query_sql,
        function_locations=function_locations,
        adapter=adapter,
    )
    query_sql = resolve_table_function_references(
        query_sql=query_sql,
        function_locations=function_locations,
        adapter=adapter,
    )
    assert_no_unresolved_sql_markers(
        sql=query_sql, context=f"Function '{function.name}' planned SQL"
    )
    return query_sql


def _compute_model_cursor_bounds(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    backfill: BackfillResult,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    suppress_runtime_cursor_bounds: bool,
) -> CursorBounds | None:
    """Compute cursor bounds for a model if it is incremental with a cursor."""

    materialized: str | None = get_config_str(model=model, key="materialized")
    cursor_column: str | None = get_config_str(model=model, key="cursor")

    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None

    incremental_mode: str | None = get_config_str(model=model, key="incremental_mode")
    is_microbatch: bool = incremental_mode == IncrementalMode.MICROBATCH
    if is_microbatch:
        return CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL)

    if full_refresh or suppress_runtime_cursor_bounds:
        return None

    if has_model_backed_cursor_inputs(
        model=model,
        model_locations=model_locations,
        seed_locations=seed_locations,
        cursor_inputs=_get_cursor_inputs(model),
    ):
        return CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL)
    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = get_config_str(model=model, key="lookback")
    cursor_start: str | None = get_config_cursor_start(model)
    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    return compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        cursor_type=get_config_str(model=model, key="cursor_type"),
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=is_microbatch,
        cursor_grain=get_config_str(model=model, key="cursor_grain"),
    )


def _get_cursor_inputs(model: CompiledModel) -> dict[str, str]:
    """Resolve cursor column mapping per upstream ref."""

    cursor_column: str | None = get_config_str(model=model, key="cursor")
    if cursor_column is None:
        return {}

    raw: object | None = model.config.values.get("cursor_inputs")
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}

    return {ref.ref_name: cursor_column for ref in model.references}
