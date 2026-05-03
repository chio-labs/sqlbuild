"""Per-model SQL resolution orchestration."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledRelationTarget,
)
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.helpers.resolve.config import (
    get_config_append_cursor_inclusive,
    get_config_cursor_start,
    get_config_str,
)
from sqlbuild.compiler.planner.helpers.resolve.cursor import compute_cursor_bounds
from sqlbuild.compiler.planner.helpers.resolve.cursor_inputs import (
    has_model_backed_cursor_inputs,
)
from sqlbuild.compiler.planner.helpers.resolve.refs import (
    resolve_dbt_ref_references,
    resolve_ref_references,
)
from sqlbuild.compiler.planner.helpers.resolve.sources import (
    resolve_source_references,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorBounds,
    ModelCursorSnapshot,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, IncrementalMode, MaterializationType
from sqlbuild.spec.models.source import SourceEntry


def resolve_model_sql(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
    backfill: BackfillResult,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
) -> str:
    """Resolve all references in a model's query SQL to produce executable SQL."""

    query_sql: str = model.query_sql

    cursor_bounds: CursorBounds | None = _compute_model_cursor_bounds(
        model=model,
        snapshot=snapshot,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        model_targets=model_targets,
        seed_targets=seed_targets,
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
        lower_bound_inclusive=lower_bound_inclusive,
    )

    query_sql = resolve_ref_references(
        query_sql=query_sql,
        model_targets=model_targets,
        seed_targets=seed_targets,
        cursor_bounds=cursor_bounds,
        cursor_inputs=cursor_inputs,
        lower_bound_inclusive=lower_bound_inclusive,
    )

    query_sql = resolve_dbt_ref_references(query_sql=query_sql)

    return query_sql


def _compute_model_cursor_bounds(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    backfill: BackfillResult,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
) -> CursorBounds | None:
    """Compute cursor bounds for a model if it is incremental with a cursor."""

    materialized: str | None = get_config_str(model, "materialized")
    cursor_column: str | None = get_config_str(model, "cursor")

    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None

    if has_model_backed_cursor_inputs(
        model=model,
        model_targets=model_targets,
        seed_targets=seed_targets,
        cursor_inputs=_get_cursor_inputs(model),
    ):
        return CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL)

    if full_refresh:
        return None

    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = get_config_str(model, "lookback")
    cursor_start: str | None = get_config_cursor_start(model)
    incremental_mode: str | None = get_config_str(model, "incremental_mode")
    is_microbatch: bool = incremental_mode == IncrementalMode.MICROBATCH

    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    return compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        cursor_type=get_config_str(model, "cursor_type"),
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=is_microbatch,
    )


def _get_cursor_inputs(model: CompiledModel) -> dict[str, str]:
    """Resolve cursor column mapping per upstream ref."""

    cursor_column: str | None = get_config_str(model, "cursor")
    if cursor_column is None:
        return {}

    raw: object | None = model.config.values.get("cursor_inputs")
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}

    return {ref.ref_name: cursor_column for ref in model.references}
