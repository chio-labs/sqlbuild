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
    CompiledSeed,
    CompiledSource,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.changes.main import detect_model_changes
from sqlbuild.compiler.planner.helpers.cursor_type_check import (
    check_cursor_type_consistency,
)
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
    CursorOverrides,
    ModelCursorSnapshot,
    ModelPlanEntry,
    PlanWarning,
    SchemaAction,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    CursorType,
    IncrementalMode,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
)
from sqlbuild.spec.models.schema import SchemaColumn
from sqlbuild.spec.models.source import SourceEntry

_MODELS_DIR_PREFIX: str = "models/"


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
    declared_columns: tuple[ColumnInfo, ...] = _get_declared_columns(model)
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
    cursor_column: str | None = _get_config_str(model, "cursor")
    cursor_type: str | None = _get_config_str(model, "cursor_type")

    cursor_type_warning: PlanWarning | None = check_cursor_type_consistency(
        model_name=model.name,
        cursor_column=cursor_column,
        cursor_type=cursor_type,
        warehouse_columns=warehouse_columns,
        sqlglot_enabled=sqlglot_enabled,
    )
    if cursor_type_warning is not None:
        warnings = (*warnings, cursor_type_warning)

    incremental_strategy: str | None = _get_config_str(model, "incremental_strategy")
    incremental_mode: str | None = _get_config_str(model, "incremental_mode")
    batch_size: str | None = _get_config_str(model, "batch_size")

    microbatch_range: CursorBounds | None = _compute_microbatch_range(
        model=model,
        snapshot=snapshot,
        backfill=backfill,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
    )

    fingerprint: Fingerprint | None = snapshot.fingerprints.get(model.name)
    previous_query_sql: str | None = fingerprint.query_sql if fingerprint is not None else None

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
        incremental_strategy=incremental_strategy,
        incremental_mode=incremental_mode,
        cursor_column=cursor_column,
        cursor_type=cursor_type,
        cursor_bounds=cursor_bounds,
        batch_size=batch_size,
        microbatch_range=microbatch_range,
        unique_key=unique_key,
        on_schema_change=on_schema_change,
        type_enforcement=type_enforcement,
        declared_columns=declared_columns,
        pre_hook=pre_hook,
        post_hook=post_hook,
        previous_query_sql=previous_query_sql,
        schema_actions=schema_actions,
        schema_findings=change_result.schema_findings,
        backfill=backfill,
    )

    return entry, warnings


def resolve_cursor_overrides(
    *,
    model: CompiledModel,
    cursor_overrides: CursorOverrides | None,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
) -> tuple[str | None, str | None]:
    """Resolve typed cursor overrides to generic start/end for one model.

    If cursor_overrides is provided, the model's cursor_type determines which
    typed field applies. Generic overrides serve as fallback.
    """

    if cursor_overrides is None:
        return start_cursor_override, end_cursor_override

    cursor_type: str | None = _get_config_str(model, "cursor_type")
    resolved_start: str | None = start_cursor_override
    resolved_end: str | None = end_cursor_override

    if cursor_type == CursorType.TIMESTAMP:
        if cursor_overrides.start_ts is not None:
            resolved_start = cursor_overrides.start_ts
        if cursor_overrides.end_ts is not None:
            resolved_end = cursor_overrides.end_ts
    elif cursor_type == CursorType.INTEGER:
        if cursor_overrides.start_int is not None:
            resolved_start = cursor_overrides.start_int
        if cursor_overrides.end_int is not None:
            resolved_end = cursor_overrides.end_int

    return resolved_start, resolved_end


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


def build_path_index(
    project: CompiledProject,
) -> dict[CompiledObjectKey, str]:
    """Build a key-to-folder lookup from compiled model relative paths.

    The folder value is the model's parent directory relative to models/,
    with the implicit models/ prefix stripped.
    """

    index: dict[CompiledObjectKey, str] = {}
    model: CompiledModel
    for model in project.models:
        parent: str = str(model.relative_path.parent)
        folder: str = _strip_models_prefix(parent)
        index[model.key] = folder
    return index


def _strip_models_prefix(path: str) -> str:
    """Strip leading models/ from a relative path string."""

    if path.startswith(_MODELS_DIR_PREFIX):
        return path[len(_MODELS_DIR_PREFIX) :]
    if path == "models":
        return ""
    return path


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


def extract_seed_columns(seed: CompiledSeed) -> tuple[ColumnInfo, ...]:
    """Extract declared columns from seed schema entry."""

    columns: list[ColumnInfo] = []
    col: SchemaColumn
    for col in seed.schema_entry.columns:
        if col.type is not None:
            columns.append(ColumnInfo(name=col.name, type=col.type))
    return tuple(columns)


def _get_type_enforcement(model: CompiledModel) -> bool:
    """Resolve whether type enforcement is active for a model."""

    if model.schema_entry is not None and model.schema_entry.type_enforcement is not None:
        return model.schema_entry.type_enforcement
    return False


def _get_declared_columns(model: CompiledModel) -> tuple[ColumnInfo, ...]:
    """Extract declared columns with types from schema entry."""

    if model.schema_entry is None:
        return ()
    columns: list[ColumnInfo] = []
    col: SchemaColumn
    for col in model.schema_entry.columns:
        if col.type is not None:
            columns.append(ColumnInfo(name=col.name, type=col.type))
    return tuple(columns)


def _get_unique_key(model: CompiledModel) -> tuple[str, ...]:
    """Extract unique_key from model config as a normalized tuple."""

    raw: object | None = model.config.values.get("unique_key")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(k for k in raw if isinstance(k, str))
    return ()


def _compute_microbatch_range(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    backfill: BackfillResult,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
) -> CursorBounds | None:
    """Compute the real overall cursor range for microbatch batch splitting."""

    materialized: str | None = _get_config_str(model, "materialized")
    if materialized != MaterializationType.INCREMENTAL:
        return None
    incremental_mode: str | None = _get_config_str(model, "incremental_mode")
    if incremental_mode != IncrementalMode.MICROBATCH:
        return None
    cursor_column: str | None = _get_config_str(model, "cursor")
    if cursor_column is None:
        return None
    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = _get_config_str(model, "lookback")
    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    return compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=False,
    )


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
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None
    if full_refresh:
        return None

    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = _get_config_str(model, "lookback")
    incremental_mode: str | None = _get_config_str(model, "incremental_mode")
    is_microbatch: bool = incremental_mode == IncrementalMode.MICROBATCH

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


def scope_overlaps(
    scope_deps: tuple[CompiledObjectKey, ...],
    selected_keys: frozenset[CompiledObjectKey],
) -> bool:
    """Check if any scope dependency is in the selected keys."""

    dep: CompiledObjectKey
    for dep in scope_deps:
        if dep in selected_keys:
            return True
    return False


def is_settings_flag(project: CompiledProject, key: str, *, default: bool) -> bool:
    """Check a boolean setting from project effective connection."""

    raw: object | None = project.effective_connection.get(key)
    if isinstance(raw, bool):
        return raw
    return default


def build_model_materializations(
    model_entries: tuple[ModelPlanEntry, ...],
) -> dict[str, str]:
    """Build a name-to-materialization-type lookup from planned model entries."""

    return {entry.name: entry.materialization_type for entry in model_entries}


def _get_config_str(model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None
