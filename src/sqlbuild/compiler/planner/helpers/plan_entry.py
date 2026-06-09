"""Per-model plan entry construction helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompileSqlReference,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.constants import (
    METADATA_NAME_FILTER_LIMIT,
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.changes.detect import detect_model_changes
from sqlbuild.compiler.planner.helpers.cursor_type_check import (
    check_cursor_type_consistency,
)
from sqlbuild.compiler.planner.helpers.resolve.cursor import (
    compute_cursor_bounds,
)
from sqlbuild.compiler.planner.helpers.resolve.refs import (
    apply_deferred_locations,
    build_function_locations,
    build_model_locations,
    build_seed_locations,
)
from sqlbuild.compiler.planner.helpers.resolve.resolve import resolve_model_sql
from sqlbuild.compiler.planner.helpers.source_deferral import build_source_read_map
from sqlbuild.compiler.planner.helpers.source_load_nodes import build_source_load_map
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
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerResolvedActions,
    PlannerScope,
    PlanWarning,
    ResolvedModelAction,
    SchemaAction,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ContractPolicy,
    CursorType,
    IncrementalMode,
    IncrementalStrategy,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
)
from sqlbuild.compiler.shared.helpers.sources import render_source_relation
from sqlbuild.shared.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.schema import SchemaColumn
from sqlbuild.spec.models.source import SourceEntry

_MODELS_DIR_PREFIX: str = "models/"
_IDEMPOTENT_MICROBATCH_STRATEGIES: frozenset[IncrementalStrategy] = frozenset(
    (IncrementalStrategy.DELETE_INSERT, IncrementalStrategy.MERGE)
)


def build_planner_relations_context(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
    defer_sources_to: str | None = None,
    source_deferral_enabled: bool = True,
) -> PlannerRelationsContext:
    """Resolve relation locations and source metadata for plan entry construction."""

    model_locations: dict[str, CompiledRelationLocation] = build_model_locations(project.models)
    seed_locations: dict[str, CompiledRelationLocation] = build_seed_locations(project.seeds)
    function_locations: dict[str, CompiledRelationLocation] = build_function_locations(
        project.functions
    )
    if deferred_locations is not None:
        apply_deferred_locations(
            model_locations=model_locations,
            seed_locations=seed_locations,
            deferred_locations=deferred_locations,
            selected_keys=scope.selected_keys,
        )
    source_map: dict[str, SourceEntry] = build_source_load_map(
        project=project,
        selected_keys=scope.selected_keys,
    )
    source_read_map: dict[str, SourceEntry] = (
        build_source_read_map(
            project=project,
            source_map=source_map,
            selected_keys=scope.selected_keys,
            project_config=project_config,
            local_config=local_config,
            defer_sources_to=defer_sources_to,
        )
        if source_deferral_enabled
        else source_map
    )
    return PlannerRelationsContext(
        model_locations=model_locations,
        seed_locations=seed_locations,
        function_locations=function_locations,
        source_map=source_map,
        source_read_map=source_read_map,
        source_warehouse_columns=gather_source_columns(
            project=project,
            adapter=adapter,
            connection=connection,
            source_entries=tuple(source_read_map.values()),
        ),
        star_exclude_keyword=adapter.star_exclude_keyword(),
    )


def plan_model(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    adapter: BaseAdapter,
    model_locations: dict[str, CompiledRelationLocation],
    models_by_name: dict[str, CompiledModel],
    seed_locations: dict[str, CompiledRelationLocation],
    function_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
    sql_analysis_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    backfill_override: BackfillResult | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> tuple[ModelPlanEntry, tuple[PlanWarning, ...]]:
    """Detect changes and build a plan entry and warnings for a single model."""

    change_result: ChangeDetectionResult = detect_model_changes(
        model=model,
        snapshot=snapshot,
        sql_analysis_enabled=sql_analysis_enabled,
        query_change_tracking=query_change_tracking,
        full_refresh=full_refresh,
    )

    return plan_model_from_change(
        model=model,
        snapshot=snapshot,
        adapter=adapter,
        model_locations=model_locations,
        models_by_name=models_by_name,
        seed_locations=seed_locations,
        function_locations=function_locations,
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
        star_exclude_keyword=star_exclude_keyword,
        sql_analysis_enabled=sql_analysis_enabled,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        change_result=change_result,
        backfill_override=backfill_override,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )


def build_plan_entries(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    relations: PlannerRelationsContext,
    resolved_actions: PlannerResolvedActions,
    cursor_overrides: CursorOverrides | None,
    full_refresh: bool,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
) -> PlannerModelEntryResults:
    """Build model plan entries from snapshot and cascade-resolved actions."""

    entries: list[ModelPlanEntry] = []
    warnings: list[PlanWarning] = []
    key: CompiledObjectKey
    for key in scope.execution_order:
        if key not in scope.selected_keys or key.name not in resolved_actions.models:
            continue
        model: CompiledModel | None = scope.models_by_name.get(key.name)
        resolved: ResolvedModelAction = resolved_actions.models[key.name]
        if model is None:
            continue
        resolved_start: str | None
        resolved_end: str | None
        resolved_start, resolved_end = resolve_cursor_overrides(
            model=model,
            cursor_overrides=cursor_overrides,
            start_cursor_override=start_cursor_override,
            end_cursor_override=end_cursor_override,
        )
        backfill_override: BackfillResult | None = (
            resolved.backfill if resolved.backfill != resolved.change.backfill else None
        )
        entry: ModelPlanEntry
        entry_warnings: tuple[PlanWarning, ...]
        entry, entry_warnings = plan_model_from_change(
            model=model,
            snapshot=snapshot,
            adapter=adapter,
            model_locations=relations.model_locations,
            models_by_name=scope.models_by_name,
            seed_locations=relations.seed_locations,
            function_locations=relations.function_locations,
            source_map=relations.source_read_map,
            source_warehouse_columns=relations.source_warehouse_columns,
            star_exclude_keyword=relations.star_exclude_keyword,
            sql_analysis_enabled=project.settings.sql_analysis,
            full_refresh=full_refresh,
            start_cursor_override=resolved_start,
            end_cursor_override=resolved_end,
            change_result=resolved.change,
            backfill_override=backfill_override,
            external_sql_reference_resolver=project.external_sql_reference_resolver,
        )
        if resolved.cascade is not None:
            entry = replace(entry, cascade=resolved.cascade)
        entries.append(entry)
        warnings.extend(entry_warnings)
    return PlannerModelEntryResults(entries=tuple(entries), warnings=tuple(warnings))


def plan_model_from_change(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    adapter: BaseAdapter,
    model_locations: dict[str, CompiledRelationLocation],
    models_by_name: dict[str, CompiledModel],
    seed_locations: dict[str, CompiledRelationLocation],
    function_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
    sql_analysis_enabled: bool,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    change_result: ChangeDetectionResult,
    backfill_override: BackfillResult | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> tuple[ModelPlanEntry, tuple[PlanWarning, ...]]:
    """Build a model plan entry from a resolved change result."""

    if backfill_override is not None:
        change_result = replace(change_result, backfill=backfill_override)

    backfill: BackfillResult = change_result.backfill
    suppress_runtime_cursor_bounds: bool = (
        backfill_override is not None and backfill_override.action == BackfillAction.FULL
    )

    resolved_sql: str = resolve_model_sql(
        adapter=adapter,
        model=model,
        snapshot=snapshot,
        model_locations=model_locations,
        seed_locations=seed_locations,
        function_locations=function_locations,
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
        star_exclude_keyword=star_exclude_keyword,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        suppress_runtime_cursor_bounds=suppress_runtime_cursor_bounds,
        external_sql_reference_resolver=external_sql_reference_resolver,
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
    contract_enforced: bool = model.config.values.get("contract") == ContractPolicy.ENFORCED
    contract_columns: tuple[ColumnInfo, ...] = _get_contract_columns(model)
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

    pre_hooks: object = model.config.values.get("pre_hooks")
    post_hooks: object = model.config.values.get("post_hooks")
    cursor_column: str | None = _get_config_str(model, "cursor")
    cursor_type: str | None = _get_config_str(model, "cursor_type")
    cursor_grain: str | None = _get_config_str(model, "cursor_grain")
    cursor_start: str | None = _get_cursor_start(model)
    cursor_input_relations: tuple[CursorInputRelation, ...] = ()
    if not suppress_runtime_cursor_bounds:
        cursor_input_relations = _build_cursor_input_relations(
            model=model,
            adapter=adapter,
            model_locations=model_locations,
            models_by_name=models_by_name,
            seed_locations=seed_locations,
            source_map=source_map,
            cursor_column=cursor_column,
        )
    validate_source_cursor_input_columns(
        model=model,
        cursor_column=cursor_column,
        models_by_name=models_by_name,
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
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
        sql_analysis_enabled=sql_analysis_enabled,
    )
    if cursor_type_warning is not None:
        warnings = (*warnings, cursor_type_warning)

    incremental_strategy: str | None = _get_config_str(model, "incremental_strategy")
    incremental_mode: str | None = _get_config_str(model, "incremental_mode")
    batch_size: str | None = _get_config_str(model, "batch_size")
    snapshot_strategy: str | None = _get_config_str(model, "snapshot_strategy")
    updated_at_column: str | None = _get_config_str(model, "updated_at")
    check_columns: tuple[str, ...] = _get_check_columns(model)
    observed_at_column: str | None = _get_config_str(model, "observed_at")
    historical_input: str | None = _get_config_str(model, "historical_input")
    valid_from_column: str | None = _get_config_str(model, "valid_from_column")
    valid_to_column: str | None = _get_config_str(model, "valid_to_column")
    initial_valid_from: str | None = _get_config_str(model, "initial_valid_from")
    invalidate_hard_deletes: bool = _get_config_bool(model, "invalidate_hard_deletes")
    snapshot_full_refresh: str | None = _get_config_str(model, "snapshot_full_refresh")
    snapshot_schema_change: str | None = _get_config_str(model, "snapshot_schema_change")

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
        destination=model.destination,
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
        destination=model.destination,
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
        snapshot_strategy=snapshot_strategy,
        updated_at_column=updated_at_column,
        check_columns=check_columns,
        observed_at_column=observed_at_column,
        historical_input=historical_input,
        valid_from_column=valid_from_column,
        valid_to_column=valid_to_column,
        initial_valid_from=initial_valid_from,
        invalidate_hard_deletes=invalidate_hard_deletes,
        snapshot_full_refresh=snapshot_full_refresh,
        snapshot_schema_change=snapshot_schema_change,
        on_schema_change=on_schema_change,
        type_enforcement=type_enforcement,
        declared_columns=declared_columns,
        contract_enforced=contract_enforced,
        contract_columns=contract_columns,
        pre_hooks=pre_hooks,
        post_hooks=post_hooks,
        previous_query_sql=previous_query_sql,
        fingerprint_metadata_json=change_result.fingerprint_metadata_json,
        previous_metadata_json=change_result.previous_metadata_json,
        fingerprint_version_hash=change_result.fingerprint_version_hash,
        previous_version_hash=change_result.previous_version_hash,
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
    source_entries: tuple[SourceEntry, ...] | None = None,
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Gather warehouse columns for all declared sources."""

    result: dict[str, tuple[ColumnInfo, ...]] = {}
    source_schemas: dict[str, set[str]] = {}
    entries: tuple[SourceEntry, ...] = (
        source_entries
        if source_entries is not None
        else tuple(source.source_entry for source in project.sources)
    )
    entry: SourceEntry
    for entry in entries:
        if entry.expression is not None:
            if entry.type_enforcement:
                column_names: tuple[str, ...] = adapter.query_column_names(
                    connection, entry.expression
                )
                result[entry.name] = tuple(ColumnInfo(name=name, type="") for name in column_names)
            continue
        schema: str | None = entry.schema
        if schema is None:
            continue
        db: str | None = entry.database
        db_key: str = db or ""
        source_schemas.setdefault(db_key, set()).add(schema)

    db_key_iter: str
    schemas: set[str]
    for db_key_iter, schemas in source_schemas.items():
        database: str | None = db_key_iter or None
        names: tuple[str, ...] | None = _build_source_table_name_filter(
            project=project,
            database=database,
            schemas=schemas,
            source_entries=entries,
        )
        all_columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
            connection,
            database=database,
            schemas=tuple(sorted(schemas)),
            names=names,
        )
        entry_iter: SourceEntry
        for entry_iter in entries:
            if entry_iter.expression is not None:
                continue
            table_name: str = entry_iter.table if entry_iter.table is not None else entry_iter.name
            cols: tuple[ColumnInfo, ...] | None = all_columns.get(table_name)
            if cols is not None:
                result[entry_iter.name] = cols

    return result


def _build_source_table_name_filter(
    *,
    project: CompiledProject,
    database: str | None,
    schemas: set[str],
    source_entries: tuple[SourceEntry, ...] | None = None,
) -> tuple[str, ...] | None:
    names: set[str] = set()
    entries: tuple[SourceEntry, ...] = (
        source_entries
        if source_entries is not None
        else tuple(source.source_entry for source in project.sources)
    )
    entry: SourceEntry
    for entry in entries:
        if entry.expression is not None or entry.schema not in schemas:
            continue
        if (entry.database or None) != database:
            continue
        names.add(entry.table if entry.table is not None else entry.name)
    if not names or len(names) > METADATA_NAME_FILTER_LIMIT:
        return None
    return tuple(sorted(names))


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


def _get_contract_columns(model: CompiledModel) -> tuple[ColumnInfo, ...]:
    if model.schema_entry is None:
        return ()
    return tuple(
        ColumnInfo(name=col.name, type=col.type or "") for col in model.schema_entry.columns
    )


def _get_unique_key(model: CompiledModel) -> tuple[str, ...]:
    """Extract unique_key from model config as a normalized tuple."""

    raw: object | None = model.config.values.get("unique_key")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(k for k in raw if isinstance(k, str))
    return ()


def _get_check_columns(model: CompiledModel) -> tuple[str, ...]:
    """Extract check_columns from model config as a normalized tuple."""

    raw: object | None = model.config.values.get("check_columns")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(column for column in raw if isinstance(column, str))
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
    destination: CompiledRelationLocation,
    unique_key: tuple[str, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
    cursor_column: str | None = None,
    cursor_bounds: CursorBounds | None = None,
) -> str:
    """Generate logical DDL using adapter render methods."""

    qualified_name: str = destination.qualified_name or destination.name

    if action == PlanAction.CREATE_VIEW:
        return ";\n\n".join(
            adapter.render_create_view_as(destination=qualified_name, sql=resolved_sql)
        )

    if action == PlanAction.CREATE_TABLE:
        return ";\n\n".join(
            adapter.render_create_table_as(destination=qualified_name, sql=resolved_sql)
        )

    if action == PlanAction.INCREMENTAL_APPEND:
        return ";\n\n".join(adapter.render_append(destination=qualified_name, sql=resolved_sql))

    if action == PlanAction.INCREMENTAL_DELETE_INSERT:
        if cursor_column is not None and cursor_bounds is not None:
            return ";\n\n".join(
                adapter.render_delete_insert_cursor(
                    destination=qualified_name,
                    sql=resolved_sql,
                    cursor_column=cursor_column,
                    cursor_start=cursor_bounds.start,
                    cursor_end=cursor_bounds.end,
                )
            )
        return ";\n\n".join(
            adapter.render_delete_insert(
                destination=qualified_name,
                sql=resolved_sql,
                unique_key=unique_key,
            )
        )

    if action == PlanAction.INCREMENTAL_MERGE:
        source_columns: tuple[str, ...] = tuple(col.name for col in warehouse_columns)
        return ";\n\n".join(
            adapter.render_merge(
                destination=qualified_name,
                sql=resolved_sql,
                unique_key=unique_key,
                source_columns=source_columns,
            )
        )

    return ""


def _build_cursor_input_relations(
    *,
    model: CompiledModel,
    adapter: BaseAdapter,
    model_locations: dict[str, CompiledRelationLocation],
    models_by_name: dict[str, CompiledModel],
    seed_locations: dict[str, CompiledRelationLocation],
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
            adapter=adapter,
            model_locations=model_locations,
            seed_locations=seed_locations,
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
                        ref.ref_kind == SqlReferenceKind.REF and ref.ref_name in model_locations
                    ),
                )
            )
    return tuple(relations)


def validate_source_cursor_input_columns(
    *,
    model: CompiledModel,
    cursor_column: str | None,
    models_by_name: dict[str, CompiledModel] | None = None,
    source_map: dict[str, SourceEntry] | None = None,
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
) -> None:
    """Validate cursor input columns using contracts before source warehouse metadata."""

    materialized: str | None = _get_config_str(model, "materialized")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return

    cursor_inputs: dict[str, str] = _get_cursor_inputs(model=model, cursor_column=cursor_column)
    effective_models_by_name: dict[str, CompiledModel] = models_by_name or {}
    effective_source_map: dict[str, SourceEntry] = source_map or {}
    ref: CompileSqlReference
    for ref in model.references:
        input_cursor_column: str | None = cursor_inputs.get(ref.ref_name)
        if input_cursor_column is None:
            continue
        if ref.ref_kind == SqlReferenceKind.REF:
            upstream_model: CompiledModel | None = effective_models_by_name.get(ref.ref_name)
            if (
                upstream_model is None
                or upstream_model.config.values.get("contract") != ContractPolicy.ENFORCED
            ):
                continue
            declared_names: tuple[str, ...] = _model_declared_column_names(upstream_model)
            if input_cursor_column.lower() in {name.lower() for name in declared_names}:
                continue
            declared_display: str = ", ".join(declared_names) or "none"
            raise PlannerInputError(
                f"model '{model.name}': cursor_inputs references model '{ref.ref_name}' "
                f"column '{input_cursor_column}', but that model contract does not expose "
                f"the column. Declared contract columns: {declared_display}",
                code="S302",
            )
        if ref.ref_kind != SqlReferenceKind.SOURCE:
            continue
        source_entry: SourceEntry | None = effective_source_map.get(ref.ref_name)
        if source_entry is not None and source_entry.contract == ContractPolicy.ENFORCED:
            declared_names = tuple(column.name for column in source_entry.columns)
            if input_cursor_column.lower() in {name.lower() for name in declared_names}:
                continue
            declared_display = ", ".join(declared_names) or "none"
            raise PlannerInputError(
                f"model '{model.name}': cursor_inputs references source '{ref.ref_name}' "
                f"column '{input_cursor_column}', but that source contract does not expose "
                f"the column. Declared contract columns: {declared_display}",
                code="S302",
            )
        known_columns: tuple[ColumnInfo, ...] | None = source_warehouse_columns.get(ref.ref_name)
        if known_columns is None:
            continue
        known_column_names: frozenset[str] = frozenset(col.name.lower() for col in known_columns)
        if input_cursor_column.lower() in known_column_names:
            continue
        known_display: str = ", ".join(col.name for col in known_columns) or "none"
        raise PlannerInputError(
            f"model '{model.name}': cursor_inputs references source '{ref.ref_name}' "
            f"column '{input_cursor_column}', but that source does not expose the column. "
            f"Known source columns: {known_display}",
            code="S302",
        )


def _model_declared_column_names(model: CompiledModel) -> tuple[str, ...]:
    if model.schema_entry is None:
        return ()
    return tuple(column.name for column in model.schema_entry.columns)


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
    adapter: BaseAdapter,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
) -> str | None:
    """Resolve one cursor input reference to a qualified relation name."""

    if ref.ref_kind == SqlReferenceKind.REF:
        target: CompiledRelationLocation | None = model_locations.get(ref.ref_name)
        if target is None:
            target = seed_locations.get(ref.ref_name)
        return target.qualified_name if target is not None else None
    if ref.ref_kind == SqlReferenceKind.SOURCE:
        source: SourceEntry | None = source_map.get(ref.ref_name)
        if source is None:
            return None
        return render_source_relation(source, adapter=adapter)
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


def build_model_materializations(
    model_entries: tuple[ModelPlanEntry, ...],
) -> dict[str, str]:
    """Build a name-to-materialization-type lookup from planned model entries."""

    return {entry.name: entry.materialization_type for entry in model_entries}


def _get_config_str(model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None


def _get_config_bool(model: CompiledModel, key: str) -> bool:
    """Extract a boolean config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, bool) else False


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
