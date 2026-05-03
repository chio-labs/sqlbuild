"""Per-model plan entry construction helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSource,
)
from sqlbuild.compiler.planner.helpers.changes.main import detect_model_changes
from sqlbuild.compiler.planner.helpers.resolve.helpers.cursor import (
    compute_cursor_bounds,
)
from sqlbuild.compiler.planner.helpers.resolve.main import resolve_model_sql
from sqlbuild.compiler.planner.helpers.strategy import (
    build_logical_ddl,
    build_model_warnings,
    resolve_model_plan_action,
    resolve_schema_actions,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    CursorBounds,
    ModelCursorSnapshot,
    ModelPlanEntry,
    PlanWarning,
    SchemaAction,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
)
from sqlbuild.spec.models.source import SourceEntry


def plan_model(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
    sqlglot_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
) -> tuple[ModelPlanEntry, tuple[PlanWarning, ...]]:
    """Build a plan entry and warnings for a single model."""

    change_result: ChangeDetectionResult = detect_model_changes(
        model=model,
        snapshot=snapshot,
        sqlglot_enabled=sqlglot_enabled,
        query_change_tracking=query_change_tracking,
        full_refresh=full_refresh,
    )

    backfill: BackfillResult = change_result.backfill

    resolved_sql: str = resolve_model_sql(
        model=model,
        snapshot=snapshot,
        model_targets=model_targets,
        seed_targets=seed_targets,
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
        star_exclude_keyword=star_exclude_keyword,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
    )

    action: PlanAction
    reason: PlanReason
    action, reason = resolve_model_plan_action(
        model=model,
        change_result=change_result,
        full_refresh=full_refresh,
    )

    on_schema_change: OnSchemaChange | None = _get_on_schema_change(model)
    schema_actions: tuple[SchemaAction, ...] = resolve_schema_actions(
        schema_findings=change_result.schema_findings,
        on_schema_change=on_schema_change,
    )

    type_enforcement: bool = _get_type_enforcement(model)
    unique_key: tuple[str, ...] = _get_unique_key(model)
    warehouse_columns: tuple[ColumnInfo, ...] = snapshot.existing_columns.get(model.name, ())

    logical_ddl: str = build_logical_ddl(
        action=action,
        resolved_sql=resolved_sql,
        target=model.target,
        unique_key=unique_key,
        warehouse_columns=warehouse_columns,
    )

    cursor_bounds: CursorBounds | None = _compute_plan_cursor_bounds(
        model=model,
        snapshot=snapshot,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
    )
    materialization_type: MaterializationType = _get_materialization_type(model)

    warnings: tuple[PlanWarning, ...] = build_model_warnings(
        model_name=model.name,
        change_result=change_result,
        schema_actions=schema_actions,
        on_schema_change=on_schema_change,
        type_enforcement=type_enforcement,
    )

    pre_hook: object = model.config.values.get("pre_hook")
    post_hook: object = model.config.values.get("post_hook")

    entry: ModelPlanEntry = ModelPlanEntry(
        key=model.key,
        name=model.name,
        relative_path=model.relative_path,
        materialization_type=materialization_type,
        action=action,
        reason=reason,
        target=model.target,
        resolved_sql=resolved_sql,
        logical_ddl=logical_ddl,
        cursor_bounds=cursor_bounds,
        type_enforcement=type_enforcement,
        pre_hook=pre_hook,
        post_hook=post_hook,
        schema_actions=schema_actions,
        schema_findings=change_result.schema_findings,
        backfill=backfill,
    )

    return entry, warnings


def build_tag_index(
    project: CompiledProject,
) -> dict[str, frozenset[CompiledObjectKey]]:
    """Build a tag-to-keys lookup from compiled model configs."""

    index: dict[str, set[CompiledObjectKey]] = {}
    model: CompiledModel
    for model in project.models:
        raw_tags: object | None = model.config.values.get("tags")
        tags: list[str] = _as_string_list(raw_tags)
        tag: str
        for tag in tags:
            index.setdefault(tag, set()).add(model.key)
    return {tag: frozenset(keys) for tag, keys in index.items()}


def _as_string_list(value: object) -> list[str]:
    """Coerce a value to a list of strings."""

    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return []


def gather_source_columns(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Gather warehouse columns for all declared sources."""

    source_schemas: dict[str, set[str]] = {}
    source: CompiledSource
    for source in project.sources:
        entry: SourceEntry = source.source_entry
        schema: str | None = entry.schema
        if schema is None:
            continue
        db: str | None = entry.database
        db_key: str = db or ""
        source_schemas.setdefault(db_key, set()).add(schema)

    result: dict[str, tuple[ColumnInfo, ...]] = {}
    db_key_iter: str
    schemas: set[str]
    for db_key_iter, schemas in source_schemas.items():
        database: str | None = db_key_iter or None
        all_columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
            connection, database=database, schemas=tuple(sorted(schemas))
        )
        source_iter: CompiledSource
        for source_iter in project.sources:
            entry_iter: SourceEntry = source_iter.source_entry
            table_name: str = entry_iter.table if entry_iter.table is not None else entry_iter.name
            cols: tuple[ColumnInfo, ...] | None = all_columns.get(table_name)
            if cols is not None:
                result[entry_iter.name] = cols

    return result


def _get_materialization_type(model: CompiledModel) -> MaterializationType:
    """Extract materialization type from model config."""

    raw: object | None = model.config.values.get("materialized")
    if isinstance(raw, str):
        try:
            return MaterializationType(raw)
        except ValueError:
            pass
    return MaterializationType.TABLE


def _get_on_schema_change(model: CompiledModel) -> OnSchemaChange | None:
    """Extract on_schema_change from model config."""

    raw: object | None = model.config.values.get("on_schema_change")
    if isinstance(raw, str):
        try:
            return OnSchemaChange(raw)
        except ValueError:
            pass
    return None


def _get_type_enforcement(model: CompiledModel) -> bool:
    """Resolve whether type enforcement is active for a model."""

    if model.schema_entry is not None and model.schema_entry.type_enforcement is not None:
        return model.schema_entry.type_enforcement
    return False


def _get_unique_key(model: CompiledModel) -> tuple[str, ...]:
    """Extract unique_key from model config as a normalized tuple."""

    raw: object | None = model.config.values.get("unique_key")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(k for k in raw if isinstance(k, str))
    return ()


def _compute_plan_cursor_bounds(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    backfill: BackfillResult,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
) -> CursorBounds | None:
    """Compute cursor bounds for inclusion on the plan entry."""

    materialized: str | None = _get_config_str(model, "materialized")
    cursor_column: str | None = _get_config_str(model, "cursor")
    if materialized != "incremental" or cursor_column is None:
        return None
    if full_refresh:
        return None

    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = _get_config_str(model, "lookback")
    incremental_mode: str | None = _get_config_str(model, "incremental_mode")
    is_microbatch: bool = incremental_mode == "microbatch"

    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    return compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=is_microbatch,
    )


def _get_config_str(model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None
