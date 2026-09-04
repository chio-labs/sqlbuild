"""Per-model plan entry construction helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._cursor_roles import resolve_cursor_input_roles
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompileSqlReference,
    CursorInputRoles,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.graph.source_load_nodes import build_source_load_map
from sqlbuild.compiler.planner._helpers.output.cursor_type_check import (
    check_cursor_type_consistency,
)
from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    resolve_bounded_cursor_override,
)
from sqlbuild.compiler.planner._helpers.output.microbatch_bounds import (
    cap_microbatch_bounds,
    validate_capped_watermark_inputs,
)
from sqlbuild.compiler.planner._helpers.output.microbatch_count import count_microbatches
from sqlbuild.compiler.planner._helpers.output.strategy import (
    build_model_warnings,
    get_materialization_type,
    resolve_model_plan_action,
    resolve_schema_actions,
)
from sqlbuild.compiler.planner._helpers.planning.full_refresh import resolve_model_full_refresh
from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    compute_cursor_bounds,
    normalize_cursor_snapshot_grain,
    resolve_effective_timestamp_grain,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor_policies import (
    resolve_future_cursor_config,
    resolve_start_cursor_config,
)
from sqlbuild.compiler.planner._helpers.resolve.lineage import resolve_lineage_reference
from sqlbuild.compiler.planner._helpers.resolve.refs import (
    apply_deferred_locations,
    build_function_locations,
    build_model_locations,
    build_seed_locations,
)
from sqlbuild.compiler.planner._helpers.resolve.resolve import resolve_model_sql
from sqlbuild.compiler.planner._helpers.warehouse.source_deferral import build_source_read_map
from sqlbuild.compiler.planner.constants import (
    METADATA_NAME_FILTER_LIMIT,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.changes._model_changes import detect_model_changes
from sqlbuild.compiler.planner.main.execution.effective_microbatch_batch_size import (
    resolve_effective_microbatch_batch_size,
)
from sqlbuild.compiler.planner.main.execution.future_cursor_safety import apply_future_cursor_safety
from sqlbuild.compiler.planner.main.execution.future_cursor_warning import future_cursor_cap_warning
from sqlbuild.compiler.planner.main.execution.maximum_start_warning import maximum_start_cap_warning
from sqlbuild.compiler.planner.main.execution.microbatch_limit import (
    _resolve_microbatch_limit_config,
    microbatch_limit_warning,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    CursorBounds,
    CursorInputEvidence,
    CursorInputRelation,
    CursorOverridePair,
    CursorOverrides,
    DeferralInputs,
    Duration,
    MaximumStartPolicyInputs,
    ModelCursorSnapshot,
    ModelPlanContext,
    ModelPlanEntry,
    PlanEntryBuildInputs,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerResolvedActions,
    PlannerScope,
    PlanWarning,
    ResolvedModelAction,
    RunDespiteUnchangedDecision,
    RunDespiteUnchangedPlanningResult,
    SchemaAction,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ContractPolicy,
    CursorGrain,
    CursorType,
    IncrementalMode,
    IncrementalStrategy,
    MaterializationType,
    MicrobatchStrategy,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    WarningSeverity,
)
from sqlbuild.compiler.references.main._render_source_relation import render_source_relation
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.sentinel_to_token import sentinel_to_token
from sqlbuild.cursor_algebra.models import TimestampValue
from sqlbuild.cursor_algebra.types import BoundSentinel
from sqlbuild.spec.contracts.models import (
    FutureCursorsConfig,
    LocalConfig,
    ProjectConfig,
    SchemaColumn,
    SourceEntry,
    StartCursorsConfig,
)
from sqlbuild.spec.contracts.types import MicrobatchLimitAction, TableType

_MODELS_DIR_PREFIX: str = "models/"
_IDEMPOTENT_MICROBATCH_STRATEGIES: frozenset[IncrementalStrategy] = frozenset(
    (IncrementalStrategy.DELETE_INSERT, IncrementalStrategy.MERGE)
)


@dataclass(frozen=True)
class _MicrobatchRangeInputs:
    snapshot: WarehouseSnapshot
    backfill: BackfillResult
    start_cursor_override: str | None
    end_cursor_override: str | None
    runtime_owned_cursor_bounds: bool
    cursor_input_relations: tuple[CursorInputRelation, ...]
    future_cursor_config: FutureCursorsConfig | None
    start_cursor_config: StartCursorsConfig | None
    invocation_time: datetime | None
    full_refresh: bool


@dataclass(frozen=True)
class _ModelPlanConfig:
    incremental_strategy: str | None
    incremental_mode: str | None
    microbatch_strategy: str | None
    cursor_watermark_mode: str | None
    batch_size: str | None
    snapshot_strategy: str | None
    updated_at_column: str | None
    check_columns: tuple[str, ...]
    observed_at_column: str | None
    historical_input: str | None
    valid_from_column: str | None
    valid_to_column: str | None
    initial_valid_from: str | None
    invalidate_hard_deletes: bool
    snapshot_full_refresh: str | None
    snapshot_schema_change: str | None


@dataclass(frozen=True)
class _CustomMaterializationConfig:
    name: str | None
    config: dict[str, object]
    placeholders: dict[str, str]


def build_planner_relations_context(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    deferral: DeferralInputs | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
    known_source_columns: dict[str, tuple[ColumnInfo, ...]] | None = None,
    relation_keys: frozenset[CompiledObjectKey] | None = None,
) -> PlannerRelationsContext:
    """Resolve relation locations and source metadata for plan entry construction."""

    effective_deferral: DeferralInputs = deferral if deferral is not None else DeferralInputs()
    model_locations: dict[str, CompiledRelationLocation] = build_model_locations(project.models)
    seed_locations: dict[str, CompiledRelationLocation] = build_seed_locations(project.seeds)
    function_locations: dict[str, CompiledRelationLocation] = build_function_locations(
        project.functions
    )
    if effective_deferral.deferred_locations is not None:
        model_locations, seed_locations = apply_deferred_locations(
            model_locations=model_locations,
            seed_locations=seed_locations,
            deferred_locations=effective_deferral.deferred_locations,
            selected_keys=scope.selected_keys,
        )
    audit_relation_keys: frozenset[CompiledObjectKey] = _selected_audit_relation_keys(
        project=project,
        selected_keys=scope.selected_keys,
    )
    source_map: dict[str, SourceEntry] = build_source_load_map(
        project=project,
        selected_keys=(
            relation_keys
            if relation_keys is not None
            else scope.selected_keys | audit_relation_keys
        ),
        upstream_deps=scope.upstream_deps if scope.all_keys else None,
    )
    source_read_map: dict[str, SourceEntry] = (
        build_source_read_map(
            project=project,
            source_map=source_map,
            selected_keys=scope.selected_keys,
            project_config=project_config,
            local_config=local_config,
            defer_sources_to=effective_deferral.defer_sources_to,
        )
        if effective_deferral.source_deferral_enabled
        else source_map
    )
    return PlannerRelationsContext(
        model_locations=model_locations,
        seed_locations=seed_locations,
        function_locations=function_locations,
        source_map=source_map,
        source_read_map=source_read_map,
        source_warehouse_columns=_resolve_source_warehouse_columns(
            project=project,
            adapter=adapter,
            connection=connection,
            source_read_map=source_read_map,
            known_source_columns=known_source_columns,
        ),
        star_exclude_keyword=adapter.star_exclude_keyword(),
    )


def _resolve_source_warehouse_columns(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    source_read_map: dict[str, SourceEntry],
    known_source_columns: dict[str, tuple[ColumnInfo, ...]] | None,
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Reuse already-gathered source columns for the read map or gather them once."""

    if known_source_columns is not None:
        return {
            name: known_source_columns[name]
            for name in source_read_map
            if name in known_source_columns
        }
    return gather_source_columns(
        project=project,
        adapter=adapter,
        connection=connection,
        source_entries=tuple(source_read_map.values()),
    )


def plan_model(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    adapter: BaseAdapter,
    context: ModelPlanContext,
    sql_analysis_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
    cursor_overrides: CursorOverridePair,
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
        context=context,
        sql_analysis_enabled=sql_analysis_enabled,
        full_refresh=full_refresh,
        cursor_overrides=cursor_overrides,
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
    build_inputs: PlanEntryBuildInputs | None = None,
) -> PlannerModelEntryResults:
    """Build model plan entries from snapshot and cascade-resolved actions."""

    inputs: PlanEntryBuildInputs = (
        build_inputs if build_inputs is not None else PlanEntryBuildInputs()
    )
    run_despite_unchanged: RunDespiteUnchangedPlanningResult | None = inputs.run_despite_unchanged
    source_freshness_blocked_model_names: frozenset[str] = (
        inputs.source_freshness_blocked_model_names
    )
    external_blocked_model_names: frozenset[str] = inputs.external_blocked_model_names
    start_cursor_override: str | None = inputs.start_cursor_override
    end_cursor_override: str | None = inputs.end_cursor_override
    entries: list[ModelPlanEntry] = []
    warnings: list[PlanWarning] = []
    runtime_cursor_producer_names: frozenset[str] = _runtime_cursor_producer_names(
        scope=scope,
        source_map=relations.source_map,
    )
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
        effective_full_refresh: bool = resolve_model_full_refresh(
            model=model,
            cli_full_refresh=full_refresh,
        )
        entry, entry_warnings = plan_model_from_change(
            model=model,
            snapshot=snapshot,
            adapter=adapter,
            context=ModelPlanContext(
                model_locations=relations.model_locations,
                models_by_name=scope.models_by_name,
                functions_by_name={function.name: function for function in project.functions},
                seed_locations=relations.seed_locations,
                function_locations=relations.function_locations,
                source_map=relations.source_read_map,
                source_warehouse_columns=relations.source_warehouse_columns,
                star_exclude_keyword=relations.star_exclude_keyword,
                runtime_cursor_producer_names=runtime_cursor_producer_names,
                future_cursor_config=inputs.future_cursor_config,
                start_cursor_config=inputs.start_cursor_config,
                invocation_time=inputs.invocation_time,
            ),
            sql_analysis_enabled=project.settings.sql_analysis,
            full_refresh=effective_full_refresh,
            cursor_overrides=CursorOverridePair(
                start_cursor_override=resolved_start,
                end_cursor_override=resolved_end,
            ),
            change_result=resolved.change,
            backfill_override=backfill_override,
            external_sql_reference_resolver=project.external_sql_reference_resolver,
        )
        if resolved.cascade is not None:
            entry = replace(entry, cascade=resolved.cascade)
        if entry.name in source_freshness_blocked_model_names:
            entry = replace(
                entry,
                action=PlanAction.SKIP,
                reason=PlanReason.SOURCE_FRESHNESS_ERROR,
            )
        if entry.name in external_blocked_model_names:
            entry = replace(
                entry,
                action=PlanAction.SKIP,
                reason=PlanReason.EXTERNAL_UPSTREAM_FAILED,
            )
        if run_despite_unchanged is not None:
            run_decision: RunDespiteUnchangedDecision | None = run_despite_unchanged.decisions.get(
                entry.name
            )
            if run_decision is not None:
                entry = replace(entry, run_despite_unchanged=run_decision)
        if entry.incremental_mode == IncrementalMode.MICROBATCH:
            entry = replace(
                entry,
                unaccounted_partition_policy=(
                    entry.unaccounted_partition_policy
                    or project.settings.microbatch_unaccounted_partition_policy
                ),
            )
            if entry.action != PlanAction.SKIP:
                entry, limit_warnings = _apply_configured_microbatch_limits(
                    entry=entry, inputs=inputs
                )
                warnings.extend(limit_warnings)
        entries.append(entry)
        warnings.extend(entry_warnings)
    configured_concurrent_entries: tuple[ModelPlanEntry, ...] = tuple(
        entry
        for entry in entries
        if entry.batch_concurrency > 1 and entry.action != PlanAction.SKIP
    )
    if configured_concurrent_entries and not project.settings.microbatch_concurrency:
        names: str = ", ".join(entry.name for entry in configured_concurrent_entries)
        raise CompileInputError(
            "batch_concurrency > 1 requires settings.microbatch_concurrency = true; "
            f"selected model(s): {names}"
        )
    if configured_concurrent_entries and not adapter.supports_concurrent_microbatch_dml():
        raise CompileInputError(
            f"adapter '{adapter.adapter_name}' does not support concurrent microbatch "
            "delete/insert DML; set batch_concurrency = 1"
        )
    concurrent_entries: tuple[ModelPlanEntry, ...] = tuple(
        entry for entry in configured_concurrent_entries if entry.action != PlanAction.CREATE_TABLE
    )
    if concurrent_entries and project.settings.concurrency > 1:
        count: int = len(concurrent_entries)
        names = ", ".join(entry.name for entry in concurrent_entries)
        warnings.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.WARNING,
                code="MICROBATCH_CONCURRENCY_COMPLEXITY",
                message=(
                    f"Concurrent microbatch execution is enabled for {count} selected "
                    f"model{'s' if count != 1 else ''}: {names}. Concurrent batches may complete "
                    "out of order and rely on persistent microbatch history for gap "
                    "recovery and fingerprint provenance. State deletion or corruption "
                    "can require synthetic reconciliation and weaken version guarantees. "
                    "Keep batch_concurrency at 1 unless the runtime benefit justifies "
                    "this complexity; see the microbatch concurrency and recovery "
                    "documentation."
                ),
            )
        )
    return PlannerModelEntryResults(entries=tuple(entries), warnings=tuple(warnings))


def _apply_configured_microbatch_limits(
    *, entry: ModelPlanEntry, inputs: PlanEntryBuildInputs
) -> tuple[ModelPlanEntry, tuple[PlanWarning, ...]]:
    """Apply CLI, project, and model policies in their documented precedence order."""

    if inputs.max_microbatches_is_override:
        limited_entry, warning = _apply_microbatch_limit(
            entry=entry,
            max_batches=inputs.max_microbatches,
            action=MicrobatchLimitAction.ERROR,
        )
        return limited_entry, (() if warning is None else (warning,))

    if entry.declared_microbatch_limit_action is not None:
        warnings: list[PlanWarning] = []
        declared_action: MicrobatchLimitAction = entry.declared_microbatch_limit_action
        if inputs.max_microbatches is not None:
            _, safety_warning = _apply_microbatch_limit(
                entry=entry,
                max_batches=inputs.max_microbatches,
                action=inputs.microbatch_limit_action,
            )
            entry = replace(
                entry,
                microbatch_safety_limit=inputs.max_microbatches,
                microbatch_safety_limit_action=inputs.microbatch_limit_action,
            )
            if safety_warning is not None:
                warnings.append(safety_warning)
        entry, model_warning = _apply_microbatch_limit(
            entry=entry,
            max_batches=entry.microbatch_limit,
            action=declared_action,
        )
        if model_warning is not None:
            warnings.append(model_warning)
        return entry, tuple(warnings)

    max_batches: int | None = (
        None
        if entry.microbatch_strategy == MicrobatchStrategy.ROLLING_WINDOW
        and entry.reason != PlanReason.FULL_REFRESH
        and entry.start_cursor_override is None
        and entry.end_cursor_override is None
        else entry.microbatch_limit or inputs.max_microbatches
    )
    limited_entry, warning = _apply_microbatch_limit(
        entry=entry,
        max_batches=max_batches,
        action=inputs.microbatch_limit_action,
    )
    return limited_entry, (() if warning is None else (warning,))


def _apply_microbatch_limit(
    *, entry: ModelPlanEntry, max_batches: int | None, action: MicrobatchLimitAction
) -> tuple[ModelPlanEntry, PlanWarning | None]:
    if entry.action == PlanAction.SKIP:
        return entry, None
    batch_count: int | None = None
    effective_batch_size: str | None = None
    if (
        entry.microbatch_range is not None
        and entry.batch_size is not None
        and entry.cursor_type is not None
    ):
        effective_grain: str | None = resolve_effective_timestamp_grain(
            cursor_type=entry.cursor_type,
            downstream_grain=entry.cursor_grain,
            microbatch_strategy=entry.microbatch_strategy,
            cursor_input_grains=tuple(
                relation.cursor_grain for relation in entry.cursor_input_relations
            ),
        )
        effective_batch_size = (
            resolve_effective_microbatch_batch_size(
                batch_size=entry.batch_size,
                effective_grain=effective_grain,
            )
            if effective_grain is not None
            else entry.batch_size
        )
        batch_count = count_microbatches(
            bounds=entry.microbatch_range,
            batch_size=effective_batch_size,
            cursor_type=entry.cursor_type,
            equal_bounds_are_batch=entry.action == PlanAction.CREATE_TABLE,
        )
    warning: str | None = (
        None
        if batch_count is None
        else microbatch_limit_warning(
            model_name=entry.name,
            max_batches=max_batches,
            batch_count=batch_count,
            action=action,
        )
    )
    limited_range: CursorBounds | None = entry.microbatch_range
    if (
        warning is not None
        and effective_batch_size is not None
        and entry.microbatch_range is not None
        and max_batches is not None
        and action
        in {
            MicrobatchLimitAction.CAP_FROM_END,
            MicrobatchLimitAction.CAP_FROM_START,
        }
    ):
        limited_range = cap_microbatch_bounds(
            bounds=entry.microbatch_range,
            batch_size=effective_batch_size,
            cursor_type=entry.cursor_type or "",
            max_batches=max_batches,
            action=action,
        )
    limited_entry: ModelPlanEntry = replace(
        entry,
        microbatch_range=limited_range,
        microbatch_limit=max_batches,
        microbatch_limit_count=batch_count,
        microbatch_limit_action=action if max_batches is not None else None,
        microbatch_limit_warning=warning,
    )
    if warning is None:
        return limited_entry, None
    if action == MicrobatchLimitAction.ERROR:
        raise CompileInputError(warning)
    return limited_entry, PlanWarning(
        model_name=entry.name,
        severity=WarningSeverity.WARNING,
        code="MICROBATCH_LIMIT_EXCEEDED",
        message=warning,
    )


def plan_model_from_change(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    adapter: BaseAdapter,
    context: ModelPlanContext,
    sql_analysis_enabled: bool,
    full_refresh: bool,
    cursor_overrides: CursorOverridePair,
    change_result: ChangeDetectionResult,
    backfill_override: BackfillResult | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> tuple[ModelPlanEntry, tuple[PlanWarning, ...]]:
    """Build a model plan entry from a resolved change result."""

    if backfill_override is not None:
        change_result = replace(change_result, backfill=backfill_override)

    start_cursor_override: str | None = cursor_overrides.start_cursor_override
    end_cursor_override: str | None = cursor_overrides.end_cursor_override
    backfill: BackfillResult = (
        BackfillResult(action=BackfillAction.FULL) if full_refresh else change_result.backfill
    )
    suppress_runtime_cursor_bounds: bool = (
        backfill_override is not None and backfill_override.action == BackfillAction.FULL
    )
    cursor_column: str | None = _get_config_str(model=model, key="cursor")
    validate_source_cursor_input_columns(
        model=model,
        cursor_column=cursor_column,
        models_by_name=context.models_by_name,
        functions_by_name=context.functions_by_name,
        source_map=context.source_map,
        source_warehouse_columns=context.source_warehouse_columns,
    )

    resolved_sql: str = resolve_model_sql(
        adapter=adapter,
        model=model,
        snapshot=snapshot,
        context=context,
        backfill=backfill,
        full_refresh=full_refresh,
        cursor_overrides=cursor_overrides,
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

    pre_hooks, post_hooks = (
        model.config.values.get("pre_hooks"),
        model.config.values.get("post_hooks"),
    )
    cursor_type: str | None = _get_config_str(model=model, key="cursor_type")
    cursor_grain: str | None = _get_config_str(model=model, key="cursor_grain")
    cursor_start: str | None = _get_cursor_start(model)
    effective_future_cursor_config, effective_start_cursor_config = _resolve_cursor_safety_configs(
        model=model, context=context
    )
    cursor_input_relations: tuple[CursorInputRelation, ...] = ()
    validate_capped_watermark_inputs(
        model=model,
        models_by_name=context.models_by_name,
        functions_by_name=context.functions_by_name,
    )
    if not suppress_runtime_cursor_bounds:
        cursor_input_relations = _build_cursor_input_relations(
            model=model,
            adapter=adapter,
            model_locations=context.model_locations,
            models_by_name=context.models_by_name,
            functions_by_name=context.functions_by_name,
            seed_locations=context.seed_locations,
            source_map=context.source_map,
            cursor_column=cursor_column,
            runtime_cursor_producer_names=context.runtime_cursor_producer_names,
        )
    runtime_owned_cursor_bounds: bool = _has_runtime_owned_cursor_watermarks(
        cursor_input_relations
    ) and not (start_cursor_override is not None and end_cursor_override is not None)
    cursor_bounds: CursorBounds | None = _compute_plan_cursor_bounds(
        model=model,
        snapshot=snapshot,
        backfill=backfill,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        runtime_owned_cursor_bounds=runtime_owned_cursor_bounds,
        future_cursor_config=effective_future_cursor_config,
        start_cursor_config=effective_start_cursor_config,
        invocation_time=context.invocation_time,
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

    plan_config: _ModelPlanConfig = _resolve_model_plan_config(model=model)

    microbatch_range: CursorBounds | None = _compute_microbatch_range(
        model=model,
        inputs=_MicrobatchRangeInputs(
            snapshot=snapshot,
            backfill=backfill,
            start_cursor_override=start_cursor_override,
            end_cursor_override=end_cursor_override,
            runtime_owned_cursor_bounds=runtime_owned_cursor_bounds,
            cursor_input_relations=cursor_input_relations,
            future_cursor_config=effective_future_cursor_config,
            start_cursor_config=effective_start_cursor_config,
            invocation_time=context.invocation_time,
            full_refresh=full_refresh,
        ),
    )

    warnings = _append_cursor_safety_warnings(
        warnings=warnings,
        model_name=model.name,
        bounds=microbatch_range or cursor_bounds,
    )

    fingerprint: Fingerprint | None = snapshot.fingerprints.models.get(model.name)
    previous_query_sql: str | None = fingerprint.definition if fingerprint is not None else None

    custom: _CustomMaterializationConfig = _resolve_custom_materialization_config(
        model=model, materialization_type=materialization_type
    )

    ddl_cursor_bounds: CursorBounds | None = (
        _build_runtime_placeholder_bounds()
        if runtime_owned_cursor_bounds and cursor_column is not None
        else (microbatch_range if microbatch_range else cursor_bounds)
    )
    logical_ddl: str = _render_table_type_ddl(
        ddl=_build_logical_ddl_from_adapter(
            adapter=adapter,
            action=action,
            resolved_sql=resolved_sql,
            destination=model.destination,
            unique_key=unique_key,
            merge_exclude_columns=_get_config_string_tuple(
                model=model, key="merge_exclude_columns"
            ),
            warehouse_columns=warehouse_columns,
            cursor_column=cursor_column,
            cursor_bounds=ddl_cursor_bounds,
            cursor_type=cursor_type,
        ),
        table_type=model.config.table_type.value.value,
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
        incremental_strategy=plan_config.incremental_strategy,
        incremental_mode=plan_config.incremental_mode,
        microbatch_strategy=plan_config.microbatch_strategy,
        cursor_watermark_mode=plan_config.cursor_watermark_mode,
        cursor_column=cursor_column,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        cursor_start=cursor_start,
        cursor_end=_get_cursor_end(model),
        lookback=(
            resolve_microbatch_lookback(
                model=model,
                effective_grain=resolve_effective_timestamp_grain(
                    cursor_type=cursor_type,
                    downstream_grain=cursor_grain,
                    microbatch_strategy=plan_config.microbatch_strategy,
                    cursor_input_grains=tuple(
                        relation.cursor_grain for relation in cursor_input_relations
                    ),
                ),
            )
            if plan_config.incremental_mode == IncrementalMode.MICROBATCH
            else _get_config_str(model=model, key="lookback")
        ),
        lookback_is_default=(
            plan_config.incremental_mode == IncrementalMode.MICROBATCH
            and _get_config_str(model=model, key="lookback") is None
        ),
        cursor_bounds=cursor_bounds,
        cursor_input_relations=cursor_input_relations,
        batch_size=plan_config.batch_size,
        batch_concurrency=_get_positive_config_int(model=model, key="batch_concurrency") or 1,
        unaccounted_partition_policy=_get_config_str(
            model=model, key="unaccounted_partition_policy"
        ),
        microbatch_range=microbatch_range,
        microbatch_limit=_resolve_microbatch_limit_config(values=model.config.values)[0],
        declared_microbatch_limit_action=_resolve_microbatch_limit_config(
            values=model.config.values
        )[1],
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        future_cursor_config=effective_future_cursor_config,
        start_cursor_config=effective_start_cursor_config,
        invocation_time=context.invocation_time,
        unique_key=unique_key,
        merge_exclude_columns=_get_config_string_tuple(model=model, key="merge_exclude_columns"),
        snapshot_strategy=plan_config.snapshot_strategy,
        updated_at_column=plan_config.updated_at_column,
        check_columns=plan_config.check_columns,
        observed_at_column=plan_config.observed_at_column,
        historical_input=plan_config.historical_input,
        valid_from_column=plan_config.valid_from_column,
        valid_to_column=plan_config.valid_to_column,
        initial_valid_from=plan_config.initial_valid_from,
        invalidate_hard_deletes=plan_config.invalidate_hard_deletes,
        snapshot_full_refresh=plan_config.snapshot_full_refresh,
        snapshot_schema_change=plan_config.snapshot_schema_change,
        table_type=model.config.table_type.value.value,
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
        query_changed=change_result.query_changed,
        config_changed=change_result.config_changed,
        schema_actions=schema_actions,
        schema_findings=change_result.schema_findings,
        backfill=backfill,
        custom_materialization_name=custom.name,
        custom_config=custom.config,
        custom_placeholders=custom.placeholders,
    )

    return entry, warnings


def resolve_cursor_overrides(
    *,
    model: CompiledModel,
    cursor_overrides: CursorOverrides | None,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
) -> tuple[str | None, str | None]:
    """Resolve typed cursor overrides to generic start/end for one model."""

    cursor_type: str | None = _get_config_str(model=model, key="cursor_type")
    resolved_start: str | None = start_cursor_override
    resolved_end: str | None = end_cursor_override

    if cursor_overrides is not None and cursor_type == CursorType.TIMESTAMP:
        if cursor_overrides.start_ts is not None:
            resolved_start = render(value=cursor_overrides.start_ts)
        if cursor_overrides.end_ts is not None:
            resolved_end = render(value=cursor_overrides.end_ts)
    elif cursor_overrides is not None and cursor_type == CursorType.INTEGER:
        if cursor_overrides.start_int is not None:
            resolved_start = render(value=cursor_overrides.start_int)
        if cursor_overrides.end_int is not None:
            resolved_end = render(value=cursor_overrides.end_int)

    cursor_start: str | None = _get_cursor_start(model)
    cursor_end: str | None = _get_cursor_end(model)
    if (
        resolved_start is not None
        and cursor_start is not None
        and _cursor_order_key(value=resolved_start, cursor_type=cursor_type)
        < _cursor_order_key(value=cursor_start, cursor_type=cursor_type)
    ):
        raise CompileInputError(
            f"model '{model.name}': explicit start {resolved_start} is before cursor_start "
            f"{cursor_start}"
        )
    if cursor_end is not None:
        if resolved_start is not None and _cursor_order_key(
            value=resolved_start, cursor_type=cursor_type
        ) >= _cursor_order_key(value=cursor_end, cursor_type=cursor_type):
            raise CompileInputError(
                f"model '{model.name}': explicit start {resolved_start} is at or beyond "
                f"exclusive cursor_end {cursor_end}"
            )
        if resolved_end is not None and _cursor_order_key(
            value=resolved_end, cursor_type=cursor_type
        ) >= _cursor_order_key(value=cursor_end, cursor_type=cursor_type):
            raise CompileInputError(
                f"model '{model.name}': explicit end {resolved_end} is at or beyond "
                f"exclusive cursor_end {cursor_end}"
            )
    return resolved_start, resolved_end


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
                    connection=connection, sql=entry.expression
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
        relations: tuple[RelationInfo, ...] = adapter.list_relations(
            connection=connection,
            database=database,
            schemas=tuple(sorted(schemas)),
            names=names,
        )
        all_columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
            adapter.get_columns_for_relations(
                connection=connection,
                relations=relations,
            )
        )
        entry_iter: SourceEntry
        for entry_iter in entries:
            if (
                entry_iter.expression is not None
                or (entry_iter.database or None) != database
                or entry_iter.schema not in schemas
            ):
                continue
            table_name: str = entry_iter.table if entry_iter.table is not None else entry_iter.name
            identity: tuple[str | None, str | None, str] = (
                None if database is None else database.lower(),
                None if entry_iter.schema is None else entry_iter.schema.lower(),
                table_name.lower(),
            )
            cols: tuple[ColumnInfo, ...] | None = all_columns.get(identity)
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


def _get_config_string_tuple(*, model: CompiledModel, key: str) -> tuple[str, ...]:
    raw: object | None = model.config.values.get(key)
    if isinstance(raw, list | tuple):
        return tuple(value for value in raw if isinstance(value, str))
    return ()


def _get_config_optional_bool(*, model: CompiledModel, key: str) -> bool | None:
    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, bool) else None


def _get_positive_config_int(*, model: CompiledModel, key: str) -> int | None:
    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else None


def _get_check_columns(model: CompiledModel) -> tuple[str, ...]:
    """Extract check_columns from model config as a normalized tuple."""

    raw: object | None = model.config.values.get("check_columns")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(column for column in raw if isinstance(column, str))
    return ()


def _resolve_cursor_safety_configs(
    *, model: CompiledModel, context: ModelPlanContext
) -> tuple[FutureCursorsConfig | None, StartCursorsConfig | None]:
    return (
        resolve_future_cursor_config(model=model, project_config=context.future_cursor_config),
        resolve_start_cursor_config(model=model, project_config=context.start_cursor_config),
    )


def _resolve_model_plan_config(*, model: CompiledModel) -> _ModelPlanConfig:
    return _ModelPlanConfig(
        incremental_strategy=_get_config_str(model=model, key="incremental_strategy"),
        incremental_mode=_get_config_str(model=model, key="incremental_mode"),
        microbatch_strategy=_get_config_str(model=model, key="microbatch_strategy"),
        cursor_watermark_mode=_get_config_str(model=model, key="cursor_watermark_mode"),
        batch_size=_get_config_str(model=model, key="batch_size"),
        snapshot_strategy=_get_config_str(model=model, key="snapshot_strategy"),
        updated_at_column=_get_config_str(model=model, key="updated_at"),
        check_columns=_get_check_columns(model),
        observed_at_column=_get_config_str(model=model, key="observed_at"),
        historical_input=_get_config_str(model=model, key="historical_input"),
        valid_from_column=_get_config_str(model=model, key="valid_from_column"),
        valid_to_column=_get_config_str(model=model, key="valid_to_column"),
        initial_valid_from=_get_config_str(model=model, key="initial_valid_from"),
        invalidate_hard_deletes=_get_config_bool(model=model, key="invalidate_hard_deletes"),
        snapshot_full_refresh=_get_config_str(model=model, key="snapshot_full_refresh"),
        snapshot_schema_change=_get_config_str(model=model, key="snapshot_schema_change"),
    )


def _resolve_custom_materialization_config(
    *, model: CompiledModel, materialization_type: MaterializationType
) -> _CustomMaterializationConfig:
    if materialization_type != MaterializationType.CUSTOM:
        return _CustomMaterializationConfig(name=None, config={}, placeholders={})
    raw_name: object | None = model.config.values.get("materialized")
    raw_config: object | None = model.config.values.get("config")
    raw_placeholders: object | None = model.config.values.get("placeholders")
    return _CustomMaterializationConfig(
        name=raw_name if isinstance(raw_name, str) else None,
        config=(
            {str(key): value for key, value in raw_config.items()}
            if isinstance(raw_config, dict)
            else {}
        ),
        placeholders=(
            {str(key): str(value) for key, value in raw_placeholders.items()}
            if isinstance(raw_placeholders, dict)
            else {}
        ),
    )


def _compute_microbatch_range(
    *, model: CompiledModel, inputs: _MicrobatchRangeInputs
) -> CursorBounds | None:
    """Compute the real overall cursor range for microbatch batch splitting."""

    materialized: str | None = _get_config_str(model=model, key="materialized")
    if materialized != MaterializationType.INCREMENTAL:
        return None
    incremental_mode: str | None = _get_config_str(model=model, key="incremental_mode")
    if incremental_mode != IncrementalMode.MICROBATCH:
        return None
    cursor_column: str | None = _get_config_str(model=model, key="cursor")
    if cursor_column is None:
        return None
    bounded_override: CursorBounds | None = resolve_bounded_cursor_override(
        start_cursor_override=inputs.start_cursor_override,
        end_cursor_override=inputs.end_cursor_override,
        cursor_type=_get_config_str(model=model, key="cursor_type"),
        cursor_grain=_get_config_str(model=model, key="cursor_grain"),
    )
    if bounded_override is not None:
        return _clamp_cursor_end(bounds=bounded_override, model=model)
    if _get_config_str(model=model, key="microbatch_strategy") == MicrobatchStrategy.ROLLING_WINDOW:
        rolling_bounds: CursorBounds | None = _rolling_window_bounds(
            model=model, invocation_time=inputs.invocation_time
        )
        if inputs.full_refresh and rolling_bounds is not None:
            cursor_start: str | None = _get_cursor_start(model)
            if cursor_start is not None:
                rolling_bounds = replace(rolling_bounds, start=cursor_start)
        return rolling_bounds
    if inputs.runtime_owned_cursor_bounds:
        return None
    cursor_snapshot: ModelCursorSnapshot | None = inputs.snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    cursor_type: str | None = _get_config_str(model=model, key="cursor_type")
    downstream_grain: str | None = _get_config_str(model=model, key="cursor_grain")
    effective_grain: str | None = resolve_effective_timestamp_grain(
        cursor_type=cursor_type,
        downstream_grain=downstream_grain,
        microbatch_strategy=_get_config_str(model=model, key="microbatch_strategy"),
        cursor_input_grains=tuple(
            relation.cursor_grain for relation in inputs.cursor_input_relations
        ),
    )
    if cursor_type == CursorType.TIMESTAMP and effective_grain is not None:
        cursor_snapshot = normalize_cursor_snapshot_grain(
            cursor_snapshot=cursor_snapshot,
            cursor_type=cursor_type,
            effective_grain=effective_grain,
        )

    lookback: str | None = resolve_microbatch_lookback(model=model, effective_grain=effective_grain)
    cursor_start: str | None = _get_cursor_start(model)
    backfill_duration: str | None = None
    if inputs.backfill.action == BackfillAction.BOUNDED:
        backfill_duration = inputs.backfill.duration

    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        cursor_type=cursor_type,
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=inputs.start_cursor_override,
        end_cursor_override=inputs.end_cursor_override,
        cursor_grain=effective_grain,
        is_microbatch=False,
        maximum_start_policy=MaximumStartPolicyInputs(
            config=inputs.start_cursor_config,
            invocation_time=inputs.invocation_time,
            incremental_strategy=_get_config_str(model=model, key="incremental_strategy"),
            incremental_mode=incremental_mode,
        ),
    )
    return _clamp_cursor_end(
        bounds=_apply_future_safety(
            bounds=bounds,
            cursor_type=cursor_type,
            cursor_grain=effective_grain,
            start_cursor_override=inputs.start_cursor_override,
            end_cursor_override=inputs.end_cursor_override,
            future_cursor_config=inputs.future_cursor_config,
            invocation_time=inputs.invocation_time,
            input_evidence=cursor_snapshot.input_evidence,
        ),
        model=model,
    )


def resolve_microbatch_lookback(
    *, model: CompiledModel, effective_grain: str | None = None
) -> str | None:
    """Resolve explicit or default lookback for one microbatch model."""

    lookback: str | None = _get_config_str(model=model, key="lookback")
    if lookback is not None:
        return lookback
    raw_strategy: str | None = _get_config_str(model=model, key="incremental_strategy")
    strategy: IncrementalStrategy | None = (
        IncrementalStrategy(raw_strategy) if raw_strategy is not None else None
    )
    if strategy not in _IDEMPOTENT_MICROBATCH_STRATEGIES:
        return None
    batch_size: str | None = _get_config_str(model=model, key="batch_size")
    if batch_size is None:
        return None
    resolved_grain: str | None = effective_grain or _get_config_str(model=model, key="cursor_grain")
    if resolved_grain is None:
        return batch_size
    return resolve_effective_microbatch_batch_size(
        batch_size=batch_size,
        effective_grain=resolved_grain,
    )


def _compute_plan_cursor_bounds(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    backfill: BackfillResult,
    full_refresh: bool,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    runtime_owned_cursor_bounds: bool,
    future_cursor_config: FutureCursorsConfig | None = None,
    start_cursor_config: StartCursorsConfig | None = None,
    invocation_time: datetime | None = None,
) -> CursorBounds | None:
    """Compute cursor bounds for inclusion on the plan entry."""

    materialized: str | None = _get_config_str(model=model, key="materialized")
    cursor_column: str | None = _get_config_str(model=model, key="cursor")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None
    bounded_override: CursorBounds | None = resolve_bounded_cursor_override(
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        cursor_type=_get_config_str(model=model, key="cursor_type"),
        cursor_grain=_get_config_str(model=model, key="cursor_grain"),
    )
    if bounded_override is not None:
        return _clamp_cursor_end(bounds=bounded_override, model=model)
    if runtime_owned_cursor_bounds:
        return None
    if full_refresh:
        return None

    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None

    lookback: str | None = _get_config_str(model=model, key="lookback")
    cursor_start: str | None = _get_cursor_start(model)
    incremental_mode: str | None = _get_config_str(model=model, key="incremental_mode")
    is_microbatch: bool = incremental_mode == IncrementalMode.MICROBATCH

    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    cursor_type: str | None = _get_config_str(model=model, key="cursor_type")
    cursor_grain: str | None = _get_config_str(model=model, key="cursor_grain")
    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=cursor_snapshot,
        cursor_type=cursor_type,
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        is_microbatch=is_microbatch,
        cursor_grain=cursor_grain,
        maximum_start_policy=MaximumStartPolicyInputs(
            config=start_cursor_config,
            invocation_time=invocation_time,
            incremental_strategy=_get_config_str(model=model, key="incremental_strategy"),
            incremental_mode=incremental_mode,
        ),
    )
    return _clamp_cursor_end(
        bounds=_apply_future_safety(
            bounds=bounds,
            cursor_type=cursor_type,
            cursor_grain=cursor_grain,
            start_cursor_override=start_cursor_override,
            end_cursor_override=end_cursor_override,
            future_cursor_config=future_cursor_config,
            invocation_time=invocation_time,
            input_evidence=cursor_snapshot.input_evidence,
        ),
        model=model,
    )


def _apply_future_safety(
    *,
    bounds: CursorBounds | None,
    cursor_type: str | None,
    cursor_grain: str | None,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    future_cursor_config: FutureCursorsConfig | None,
    invocation_time: datetime | None,
    input_evidence: tuple[CursorInputEvidence, ...],
) -> CursorBounds | None:
    if bounds is None:
        return None
    if bounds.end == BoundSentinel.END:
        return bounds
    return apply_future_cursor_safety(
        bounds=bounds,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        config=future_cursor_config,
        invocation_time=invocation_time,
        has_complete_override=(
            start_cursor_override is not None and end_cursor_override is not None
        ),
        input_evidence=input_evidence,
    )


def _append_future_cap_warning(
    *, warnings: tuple[PlanWarning, ...], model_name: str, bounds: CursorBounds | None
) -> tuple[PlanWarning, ...]:
    message: str | None = future_cursor_cap_warning(bounds)
    if message is None:
        return warnings
    return (
        *warnings,
        PlanWarning(
            model_name=model_name,
            severity=WarningSeverity.WARNING,
            code="FUTURE_CURSOR_CAPPED",
            message=message,
        ),
    )


def _append_cursor_safety_warnings(
    *, warnings: tuple[PlanWarning, ...], model_name: str, bounds: CursorBounds | None
) -> tuple[PlanWarning, ...]:
    with_future: tuple[PlanWarning, ...] = _append_future_cap_warning(
        warnings=warnings, model_name=model_name, bounds=bounds
    )
    return _append_maximum_start_warning(warnings=with_future, model_name=model_name, bounds=bounds)


def _append_maximum_start_warning(
    *, warnings: tuple[PlanWarning, ...], model_name: str, bounds: CursorBounds | None
) -> tuple[PlanWarning, ...]:
    message: str | None = maximum_start_cap_warning(bounds)
    if message is None:
        return warnings
    return (
        *warnings,
        PlanWarning(
            model_name=model_name,
            severity=WarningSeverity.WARNING,
            code="AUTOMATIC_START_CAPPED",
            message=message,
        ),
    )


def _render_table_type_ddl(*, ddl: str, table_type: str) -> str:
    """Render permanent Snowflake table DDL from the adapter's transient default."""

    return ddl.replace("TRANSIENT TABLE", "TABLE", 1) if table_type == TableType.PERMANENT else ddl


def _build_logical_ddl_from_adapter(
    *,
    adapter: BaseAdapter,
    action: PlanAction,
    resolved_sql: str,
    destination: CompiledRelationLocation,
    unique_key: tuple[str, ...],
    merge_exclude_columns: tuple[str, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
    cursor_column: str | None = None,
    cursor_bounds: CursorBounds | None = None,
    cursor_type: str | None = None,
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
                    cursor_start=sentinel_to_token(sentinel=cursor_bounds.start),
                    cursor_end=sentinel_to_token(sentinel=cursor_bounds.end),
                    cursor_type=cursor_type,
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
                exclude_columns=merge_exclude_columns,
            )
        )

    return ""


def _build_cursor_input_relations(
    *,
    model: CompiledModel,
    adapter: BaseAdapter,
    model_locations: dict[str, CompiledRelationLocation],
    models_by_name: dict[str, CompiledModel],
    functions_by_name: dict[str, CompiledFunction] | None = None,
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    cursor_column: str | None,
    runtime_cursor_producer_names: frozenset[str],
) -> tuple[CursorInputRelation, ...]:
    """Build cursor-bearing input relation metadata for runtime range discovery."""

    materialized: str | None = _get_config_str(model=model, key="materialized")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return ()

    cursor_watermark_inputs: dict[str, str] = resolve_cursor_input_roles(
        model=model
    ).watermark_inputs
    relations: list[CursorInputRelation] = []
    input_name: str
    input_cursor_column: str
    for input_name, input_cursor_column in cursor_watermark_inputs.items():
        ref: CompileSqlReference = resolve_lineage_reference(
            model=model,
            input_name=input_name,
            models_by_name=models_by_name,
            functions_by_name=functions_by_name or {},
        )
        producer_model: CompiledModel | None = (
            models_by_name.get(ref.ref_name) if ref.ref_kind == SqlReferenceKind.REF else None
        )
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
                    cursor_grain=(
                        CursorGrain(input_grain)
                        if (
                            input_grain := _resolve_cursor_input_grain(
                                ref=ref, models_by_name=models_by_name
                            )
                        )
                        is not None
                        else None
                    ),
                    is_model_backed=(
                        ref.ref_kind == SqlReferenceKind.REF and ref.ref_name in model_locations
                    ),
                    is_runtime_produced=ref.ref_name in runtime_cursor_producer_names,
                    terminal_cursor_start=(
                        parse(
                            raw=_get_cursor_start(producer_model),
                            cursor_type=_get_config_str(model=model, key="cursor_type")
                            or CursorType.TIMESTAMP,
                        )
                        if producer_model is not None
                        and _get_cursor_start(producer_model) is not None
                        else None
                    ),
                    terminal_cursor_end=(
                        parse(
                            raw=_get_cursor_end(producer_model),
                            cursor_type=_get_config_str(model=model, key="cursor_type")
                            or CursorType.TIMESTAMP,
                        )
                        if producer_model is not None
                        and _get_cursor_end(producer_model) is not None
                        else None
                    ),
                )
            )
    return tuple(relations)


def validate_source_cursor_input_columns(
    *,
    model: CompiledModel,
    cursor_column: str | None,
    models_by_name: dict[str, CompiledModel] | None = None,
    functions_by_name: dict[str, CompiledFunction] | None = None,
    source_map: dict[str, SourceEntry] | None = None,
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
) -> None:
    """Validate cursor input columns using contracts before source warehouse metadata."""

    materialized: str | None = _get_config_str(model=model, key="materialized")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return

    cursor_roles: CursorInputRoles = resolve_cursor_input_roles(model=model)
    effective_models_by_name: dict[str, CompiledModel] = models_by_name or {}
    effective_source_map: dict[str, SourceEntry] = source_map or {}
    authored_inputs: tuple[tuple[str, str, str], ...] = tuple(
        (cursor_roles.filter_field, name, column)
        for name, column in cursor_roles.filter_inputs.items()
    ) + tuple(
        (cursor_roles.watermark_field, name, column)
        for name, column in cursor_roles.watermark_inputs.items()
    )
    config_field: str
    input_name: str
    input_cursor_column: str
    for config_field, input_name, input_cursor_column in authored_inputs:
        ref: CompileSqlReference = resolve_lineage_reference(
            model=model,
            input_name=input_name,
            models_by_name=effective_models_by_name,
            functions_by_name=functions_by_name or {},
        )
        if ref.ref_kind == SqlReferenceKind.REF:
            upstream_model: CompiledModel | None = effective_models_by_name.get(ref.ref_name)
            if upstream_model is None:
                continue
            has_enforced_contract: bool = (
                upstream_model.config.values.get("contract") == ContractPolicy.ENFORCED
            )
            if not has_enforced_contract:
                continue
            declared_names: tuple[str, ...] = _model_declared_column_names(upstream_model)
            if input_cursor_column.lower() in {name.lower() for name in declared_names}:
                continue
            declared_display: str = ", ".join(declared_names) or "none"
            raise PlannerInputError(
                f"model '{model.name}': {config_field} references model '{ref.ref_name}' "
                f"column '{input_cursor_column}', but that model contract does not expose "
                f"the column. Known output columns: {declared_display}",
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
                f"model '{model.name}': {config_field} references source '{ref.ref_name}' "
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
            f"model '{model.name}': {config_field} references source '{ref.ref_name}' "
            f"column '{input_cursor_column}', but that source does not expose the column. "
            f"Known source columns: {known_display}",
            code="S302",
        )


def _model_declared_column_names(model: CompiledModel) -> tuple[str, ...]:
    if model.schema_entry is None:
        return ()
    return tuple(column.name for column in model.schema_entry.columns)


def _has_runtime_owned_cursor_watermarks(
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> bool:
    """Return whether any cursor input is produced by this invocation."""

    return any(relation.is_runtime_owned for relation in cursor_input_relations)


def _runtime_cursor_producer_names(
    *, scope: PlannerScope, source_map: dict[str, SourceEntry]
) -> frozenset[str]:
    """Return selected relations whose contents are produced during this invocation."""

    names: set[str] = set()
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type in {CompiledResourceType.MODEL, CompiledResourceType.SEED}:
            names.add(key.name)
        elif key.resource_type == CompiledResourceType.SOURCE:
            source: SourceEntry | None = source_map.get(key.name)
            if source is not None and source.loader is not None:
                names.add(key.name)
    return frozenset(names)


def _build_runtime_placeholder_bounds() -> CursorBounds:
    """Return placeholder cursor bounds for runtime-owned models."""

    return CursorBounds(start=BoundSentinel.START, end=BoundSentinel.END)


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
    if ref.ref_kind == SqlReferenceKind.SEED:
        seed_target: CompiledRelationLocation | None = seed_locations.get(ref.ref_name)
        return seed_target.qualified_name if seed_target is not None else None
    if ref.ref_kind == SqlReferenceKind.SOURCE:
        source: SourceEntry | None = source_map.get(ref.ref_name)
        if source is None:
            return None
        return render_source_relation(entry=source, adapter=adapter)
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
    return _get_config_str(model=upstream_model, key="cursor_grain")


def scope_overlaps(
    *,
    scope_deps: tuple[CompiledObjectKey, ...],
    selected_keys: frozenset[CompiledObjectKey],
) -> bool:
    """Check if any scope dependency is in the selected keys."""

    dep: CompiledObjectKey
    for dep in scope_deps:
        if dep in selected_keys:
            return True
    return False


def audit_is_selected(
    *,
    audit: CompiledAudit,
    selected_keys: frozenset[CompiledObjectKey],
) -> bool:
    """Return whether an audit belongs to the selected logical target scope."""

    if audit.attached_target_kind is not None and audit.attached_target_name is not None:
        resource_type: CompiledResourceType = (
            CompiledResourceType.SOURCE
            if audit.attached_target_kind == AttachedAuditTargetKind.SOURCE
            else CompiledResourceType.MODEL
        )
        target_key: CompiledObjectKey = CompiledObjectKey(
            resource_type=resource_type,
            name=audit.attached_target_name,
        )
        return target_key in selected_keys
    return scope_overlaps(scope_deps=audit.scope_deps, selected_keys=selected_keys)


def _selected_audit_relation_keys(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey],
) -> frozenset[CompiledObjectKey]:
    """Return relation keys needed to render selected audits without selecting those relations."""

    relation_keys: set[CompiledObjectKey] = set()
    audit: CompiledAudit
    for audit in project.audits:
        if audit_is_selected(audit=audit, selected_keys=selected_keys):
            relation_keys.update(audit.scope_deps)
    return frozenset(relation_keys)


def build_model_materializations(
    model_entries: tuple[ModelPlanEntry, ...],
) -> dict[str, str]:
    """Build a name-to-materialization-type lookup from planned model entries."""

    return {entry.name: entry.materialization_type for entry in model_entries}


def _get_config_str(*, model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None


def _get_config_bool(*, model: CompiledModel, key: str) -> bool:
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


def _get_cursor_end(model: CompiledModel) -> str | None:
    """Extract exclusive cursor_end as a normalized string value."""

    raw: object | None = model.config.values.get("cursor_end")
    if raw is None:
        return None
    if isinstance(raw, (date, datetime)):
        return raw.isoformat()
    return str(raw)


def _rolling_window_bounds(
    *, model: CompiledModel, invocation_time: datetime | None
) -> CursorBounds | None:
    grain: str | None = _get_config_str(model=model, key="cursor_grain")
    lookback: str | None = resolve_microbatch_lookback(model=model, effective_grain=grain)
    duration: Duration | None = Duration.parse(lookback or "")
    if grain is None or duration is None:
        return None
    moment: datetime = invocation_time or datetime.now(tz=UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    else:
        moment = moment.astimezone(UTC)
    anchor: datetime = _floor_utc_grain(moment=moment, grain=grain)
    bounds: CursorBounds = CursorBounds(
        start=TimestampValue(value=duration.subtract_from(anchor)),
        end=TimestampValue(value=anchor),
    )
    cursor_start: str | None = _get_cursor_start(model)
    if cursor_start is not None and _cursor_order_key(
        value=sentinel_to_token(sentinel=bounds.start), cursor_type=CursorType.TIMESTAMP
    ) < _cursor_order_key(value=cursor_start, cursor_type=CursorType.TIMESTAMP):
        bounds = replace(bounds, start=cursor_start)
    return _clamp_cursor_end(bounds=bounds, model=model)


def _floor_utc_grain(*, moment: datetime, grain: str) -> datetime:
    if grain == CursorGrain.YEAR:
        return moment.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if grain == CursorGrain.MONTH:
        return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if grain == CursorGrain.DAY:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if grain == CursorGrain.HOUR:
        return moment.replace(minute=0, second=0, microsecond=0)
    if grain == CursorGrain.MINUTE:
        return moment.replace(second=0, microsecond=0)
    return moment.replace(microsecond=0)


def _clamp_cursor_end(*, bounds: CursorBounds | None, model: CompiledModel) -> CursorBounds | None:
    cursor_end: str | None = _get_cursor_end(model)
    cursor_type: str | None = _get_config_str(model=model, key="cursor_type")
    if bounds is None or cursor_end is None:
        return bounds
    if bounds.start == BoundSentinel.START or bounds.end == BoundSentinel.END:
        return bounds
    if _cursor_order_key(
        value=sentinel_to_token(sentinel=bounds.start), cursor_type=cursor_type
    ) >= _cursor_order_key(value=cursor_end, cursor_type=cursor_type):
        return replace(bounds, start=cursor_end, end=cursor_end)
    if _cursor_order_key(
        value=sentinel_to_token(sentinel=bounds.end), cursor_type=cursor_type
    ) > _cursor_order_key(value=cursor_end, cursor_type=cursor_type):
        return replace(bounds, end=cursor_end)
    return bounds


def _cursor_order_key(*, value: str, cursor_type: str | None) -> Decimal:
    if cursor_type == CursorType.INTEGER:
        return Decimal(value)
    parsed: datetime = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return Decimal(str(parsed.replace(tzinfo=UTC).timestamp()))
