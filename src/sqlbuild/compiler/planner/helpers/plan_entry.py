"""Per-model plan entry construction helpers."""

from __future__ import annotations

from datetime import date, datetime
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
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import SqlReferenceKind
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.helpers.changes.detect import detect_model_changes
from sqlbuild.compiler.planner.helpers.cursor_type_check import (
    check_cursor_type_consistency,
)
from sqlbuild.compiler.planner.helpers.resolve.cursor import (
    compute_cursor_bounds,
)
from sqlbuild.compiler.planner.helpers.resolve.resolve import resolve_model_sql
from sqlbuild.compiler.planner.helpers.strategy import (
    build_model_warnings,
    get_materialization_type,
    resolve_model_plan_action,
    resolve_schema_actions,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    CursorBounds,
    CursorInputRelation,
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
    IncrementalStrategy,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
)
from sqlbuild.compiler.shared.helpers.sources import render_source_relation
from sqlbuild.spec.models.schema import SchemaColumn
from sqlbuild.spec.models.source import SourceEntry

_MODELS_DIR_PREFIX: str = "models/"
_IDEMPOTENT_MICROBATCH_STRATEGIES: frozenset[IncrementalStrategy] = frozenset(
    (IncrementalStrategy.DELETE_INSERT, IncrementalStrategy.MERGE)
)


def plan_model(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    adapter: BaseAdapter,
    model_targets: dict[str, CompiledRelationTarget],
    models_by_name: dict[str, CompiledModel],
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

    materialization_type: MaterializationType = get_materialization_type(model)

    warnings: tuple[PlanWarning, ...] = build_model_warnings(
        model_name=model.name,
        materialization_type=materialization_type,
        change_result=change_result,
        schema_actions=schema_actions,
        on_schema_change=on_schema_change,
        type_enforcement=type_enforcement,
    )

    pre_hook: object = model.config.values.get("pre_hook")
    post_hook: object = model.config.values.get("post_hook")
    cursor_column: str | None = _get_config_str(model, "cursor")
    cursor_type: str | None = _get_config_str(model, "cursor_type")
    cursor_grain: str | None = _get_config_str(model, "cursor_grain")
    cursor_start: str | None = _get_cursor_start(model)
    cursor_input_relations: tuple[CursorInputRelation, ...] = _build_cursor_input_relations(
        model=model,
        model_targets=model_targets,
        models_by_name=models_by_name,
        seed_targets=seed_targets,
        source_map=source_map,
        cursor_column=cursor_column,
    )
    runtime_owned_cursor_bounds: bool = _has_model_backed_cursor_inputs(cursor_input_relations)
    cursor_bounds: CursorBounds | None = _compute_plan_cursor_bounds(
        model=model,
        snapshot=snapshot,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        runtime_owned_cursor_bounds=runtime_owned_cursor_bounds,
    )

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
        runtime_owned_cursor_bounds=runtime_owned_cursor_bounds,
    )

    fingerprint: Fingerprint | None = snapshot.fingerprints.get(model.name)
    previous_query_sql: str | None = fingerprint.query_sql if fingerprint is not None else None

    custom_materialization_name: str | None = None
    custom_config: dict[str, object] = {}
    custom_placeholders: dict[str, str] = {}
    if materialization_type == MaterializationType.CUSTOM:
        raw_materialized: object | None = model.config.values.get("materialized")
        custom_materialization_name = (
            raw_materialized if isinstance(raw_materialized, str) else None
        )
        raw_config: object | None = model.config.values.get("config")
        if isinstance(raw_config, dict):
            custom_config = {str(k): v for k, v in raw_config.items()}
        raw_placeholders: object | None = model.config.values.get("placeholders")
        if isinstance(raw_placeholders, dict):
            custom_placeholders = {str(k): str(v) for k, v in raw_placeholders.items()}

    ddl_cursor_bounds: CursorBounds | None = (
        _build_runtime_placeholder_bounds()
        if runtime_owned_cursor_bounds and cursor_column is not None
        else (microbatch_range if microbatch_range else cursor_bounds)
    )
    logical_ddl: str = _build_logical_ddl_from_adapter(
        adapter=adapter,
        action=action,
        resolved_sql=resolved_sql,
        target=model.target,
        unique_key=unique_key,
        warehouse_columns=warehouse_columns,
        cursor_column=cursor_column,
        cursor_bounds=ddl_cursor_bounds,
    )

    entry: ModelPlanEntry = ModelPlanEntry(
        key=model.key,
        name=model.name,
        relative_path=model.relative_path,
        materialization_type=materialization_type,
        action=action,
        reason=reason,
        target=model.target,
        fingerprint_query_sql=model.query_sql,
        resolved_sql=resolved_sql,
        logical_ddl=logical_ddl,
        incremental_strategy=incremental_strategy,
        incremental_mode=incremental_mode,
        cursor_column=cursor_column,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        cursor_start=cursor_start,
        cursor_bounds=cursor_bounds,
        cursor_input_relations=cursor_input_relations,
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
        custom_materialization_name=custom_materialization_name,
        custom_config=custom_config,
        custom_placeholders=custom_placeholders,
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
        if entry.expression is not None:
            continue
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
            if entry_iter.expression is not None:
                continue
            table_name: str = entry_iter.table if entry_iter.table is not None else entry_iter.name
            cols: tuple[ColumnInfo, ...] | None = all_columns.get(table_name)
            if cols is not None:
                result[entry_iter.name] = cols

    return result


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
    runtime_owned_cursor_bounds: bool,
) -> CursorBounds | None:
    """Compute the real overall cursor range for microbatch batch splitting."""

    materialized: str | None = _get_config_str(model, "materialized")
    if materialized != MaterializationType.INCREMENTAL:
        return None
    incremental_mode: str | None = _get_config_str(model, "incremental_mode")
    if incremental_mode != IncrementalMode.MICROBATCH:
        return None
    if runtime_owned_cursor_bounds:
        return None
    cursor_column: str | None = _get_config_str(model, "cursor")
    if cursor_column is None:
        return None
    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = resolve_microbatch_lookback(model)
    cursor_start: str | None = _get_cursor_start(model)
    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    return compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        cursor_type=_get_config_str(model, "cursor_type"),
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=False,
    )


def resolve_microbatch_lookback(model: CompiledModel) -> str | None:
    """Resolve explicit or default lookback for one microbatch model."""

    lookback: str | None = _get_config_str(model, "lookback")
    if lookback is not None:
        return lookback
    raw_strategy: str | None = _get_config_str(model, "incremental_strategy")
    strategy: IncrementalStrategy | None = (
        IncrementalStrategy(raw_strategy) if raw_strategy is not None else None
    )
    if strategy not in _IDEMPOTENT_MICROBATCH_STRATEGIES:
        return None
    return _get_config_str(model, "batch_size")


def _compute_plan_cursor_bounds(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    backfill: BackfillResult,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    runtime_owned_cursor_bounds: bool,
) -> CursorBounds | None:
    """Compute cursor bounds for inclusion on the plan entry."""

    materialized: str | None = _get_config_str(model, "materialized")
    cursor_column: str | None = _get_config_str(model, "cursor")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None
    if runtime_owned_cursor_bounds:
        return None
    if full_refresh:
        return None

    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = _get_config_str(model, "lookback")
    cursor_start: str | None = _get_cursor_start(model)
    incremental_mode: str | None = _get_config_str(model, "incremental_mode")
    is_microbatch: bool = incremental_mode == IncrementalMode.MICROBATCH

    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    return compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        cursor_type=_get_config_str(model, "cursor_type"),
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=is_microbatch,
    )


def _build_logical_ddl_from_adapter(
    *,
    adapter: BaseAdapter,
    action: PlanAction,
    resolved_sql: str,
    target: CompiledRelationTarget,
    unique_key: tuple[str, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
    cursor_column: str | None = None,
    cursor_bounds: CursorBounds | None = None,
) -> str:
    """Generate logical DDL using adapter render methods."""

    qualified_name: str = target.qualified_name or target.name

    if action == PlanAction.CREATE_VIEW:
        return ";\n\n".join(adapter.render_create_view_as(target=qualified_name, sql=resolved_sql))

    if action == PlanAction.CREATE_TABLE:
        return ";\n\n".join(adapter.render_create_table_as(target=qualified_name, sql=resolved_sql))

    if action == PlanAction.INCREMENTAL_APPEND:
        return ";\n\n".join(adapter.render_append(target=qualified_name, sql=resolved_sql))

    if action == PlanAction.INCREMENTAL_DELETE_INSERT:
        if cursor_column is not None and cursor_bounds is not None:
            return ";\n\n".join(
                adapter.render_delete_insert_cursor(
                    target=qualified_name,
                    sql=resolved_sql,
                    cursor_column=cursor_column,
                    cursor_start=cursor_bounds.start,
                    cursor_end=cursor_bounds.end,
                )
            )
        return ";\n\n".join(
            adapter.render_delete_insert(
                target=qualified_name,
                sql=resolved_sql,
                unique_key=unique_key,
            )
        )

    if action == PlanAction.INCREMENTAL_MERGE:
        source_columns: tuple[str, ...] = tuple(col.name for col in warehouse_columns)
        return ";\n\n".join(
            adapter.render_merge(
                target=qualified_name,
                sql=resolved_sql,
                unique_key=unique_key,
                source_columns=source_columns,
            )
        )

    return ""


def _build_cursor_input_relations(
    *,
    model: CompiledModel,
    model_targets: dict[str, CompiledRelationTarget],
    models_by_name: dict[str, CompiledModel],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    cursor_column: str | None,
) -> tuple[CursorInputRelation, ...]:
    """Build cursor-bearing input relation metadata for runtime range discovery."""

    materialized: str | None = _get_config_str(model, "materialized")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return ()

    cursor_inputs: dict[str, str] = _get_cursor_inputs(model=model, cursor_column=cursor_column)
    relations: list[CursorInputRelation] = []
    ref: CompileSqlReference
    for ref in model.references:
        input_cursor_column: str | None = cursor_inputs.get(ref.ref_name)
        if input_cursor_column is None:
            continue
        relation: str | None = _resolve_cursor_input_relation(
            ref=ref,
            model_targets=model_targets,
            seed_targets=seed_targets,
            source_map=source_map,
        )
        if relation is not None:
            relations.append(
                CursorInputRelation(
                    relation=relation,
                    cursor_column=input_cursor_column,
                    cursor_grain=_resolve_cursor_input_grain(
                        ref=ref,
                        models_by_name=models_by_name,
                    ),
                    is_model_backed=(
                        ref.ref_kind == SqlReferenceKind.REF and ref.ref_name in model_targets
                    ),
                )
            )
    return tuple(relations)


def _has_model_backed_cursor_inputs(
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> bool:
    """Return whether any cursor input relation is backed by another model."""

    return any(relation.is_model_backed for relation in cursor_input_relations)


def _build_runtime_placeholder_bounds() -> CursorBounds:
    """Return placeholder cursor bounds for runtime-owned models."""

    return CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL)


def _resolve_cursor_input_relation(
    *,
    ref: CompileSqlReference,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
) -> str | None:
    """Resolve one cursor input reference to a qualified relation name."""

    if ref.ref_kind == SqlReferenceKind.REF:
        target: CompiledRelationTarget | None = model_targets.get(ref.ref_name)
        if target is None:
            target = seed_targets.get(ref.ref_name)
        return target.qualified_name if target is not None else None
    if ref.ref_kind == SqlReferenceKind.SOURCE:
        source: SourceEntry | None = source_map.get(ref.ref_name)
        if source is None:
            return None
        return render_source_relation(source)
    return None


def _resolve_cursor_input_grain(
    *,
    ref: CompileSqlReference,
    models_by_name: dict[str, CompiledModel],
) -> str | None:
    """Resolve timestamp grain metadata for a model-backed cursor input relation."""

    if ref.ref_kind != SqlReferenceKind.REF:
        return None
    upstream_model: CompiledModel | None = models_by_name.get(ref.ref_name)
    if upstream_model is None:
        return None
    return _get_config_str(upstream_model, "cursor_grain")


def _get_cursor_inputs(model: CompiledModel, cursor_column: str) -> dict[str, str]:
    """Resolve cursor column mapping per input reference."""

    raw: object | None = model.config.values.get("cursor_inputs")
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
    return {ref.ref_name: cursor_column for ref in model.references}


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


def _get_cursor_start(model: CompiledModel) -> str | None:
    """Extract cursor_start as a normalized string value."""

    raw: object | None = model.config.values.get("cursor_start")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    if isinstance(raw, str):
        return raw
    return str(raw)
