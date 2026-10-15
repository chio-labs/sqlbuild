"""Per-model plan entry construction helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlbuild._native import (
    apply_configured_microbatch_limits,
    assemble_model_plan_entry,
    audit_is_selected,
    build_cursor_input_relations,
    build_source_load_map,
    detect_model_changes,
    get_config_cursor_bound,
    get_config_str,
    get_materialization_type,
    microbatch_guidance,
    replaces_incremental_relation,
    resolve_bounded_cursor_override,
    resolve_microbatch_lookback,
    resolve_model_plan_action,
    runtime_cursor_producer_names,
    source_binding_diagnostics,
    validate_capped_watermark_inputs,
    validate_source_cursor_input_columns,
)
from sqlbuild._native import cursor_render as render
from sqlbuild._native import cursor_sentinel_to_token as sentinel_to_token
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import (
    CompiledAuditView,
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
)
from sqlbuild.compiler.planner._helpers.planning.full_refresh import (
    check_full_rebuild_allowed,
    describe_full_rebuild_cause,
    resolve_model_full_refresh,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    compute_cursor_bounds,
    cursor_inputs_without_rows,
    normalize_cursor_snapshot_grain,
    resolve_effective_timestamp_grain,
    without_destination_cursor,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor_policies import (
    resolve_future_cursor_config,
    resolve_start_cursor_config,
)
from sqlbuild.compiler.planner._helpers.resolve.refs import (
    apply_deferred_locations,
    build_function_locations,
    build_model_locations,
    build_seed_locations,
)
from sqlbuild.compiler.planner._helpers.resolve.resolve import (
    resolve_model_hook_entries,
    resolve_model_sql,
)
from sqlbuild.compiler.planner._helpers.warehouse.semantic_sources import (
    get_semantic_source_columns,
)
from sqlbuild.compiler.planner._helpers.warehouse.source_columns import gather_source_inspection
from sqlbuild.compiler.planner._helpers.warehouse.source_deferral import (
    build_source_read_map,
    with_declared_source_reads,
)
from sqlbuild.compiler.planner.constants import MICROBATCH_CONCURRENCY_MESSAGE
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.execution.future_cursor_safety import apply_future_cursor_safety
from sqlbuild.compiler.planner.main.execution.future_cursor_warning import future_cursor_cap_warning
from sqlbuild.compiler.planner.main.execution.maximum_start_warning import maximum_start_cap_warning
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
    EmptyCursorInputDecision,
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
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    CursorGrain,
    CursorType,
    IncrementalMode,
    MaterializationType,
    MicrobatchStrategy,
    PlanAction,
    PlanReason,
    WarningSeverity,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.cursor_algebra.models import TimestampValue
from sqlbuild.cursor_algebra.types import BoundSentinel
from sqlbuild.spec.contracts.models import (
    FutureCursorsConfig,
    LocalConfig,
    ProjectConfig,
    SourceEntry,
    StartCursorsConfig,
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
    replaces_relation: bool = False


def build_planner_relations_context(
    *,
    project: CompiledProjectView,
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
    python_source_map: dict[str, SourceEntry] = with_declared_source_reads(
        project=project, source_map=source_map, source_names=scope.python_read_source_names
    )
    python_source_read_map: dict[str, SourceEntry] = (
        build_source_read_map(
            project=project,
            source_map=python_source_map,
            selected_keys=scope.selected_keys,
            project_config=project_config,
            local_config=local_config,
            defer_sources_to=effective_deferral.defer_sources_to,
            read_source_names=frozenset(python_source_map),
        )
        if effective_deferral.source_deferral_enabled
        else python_source_map
    )
    source_columns: dict[str, tuple[ColumnInfo, ...]]
    listed_source_names: frozenset[str]
    source_columns, listed_source_names = _resolve_source_warehouse_columns(
        project=project,
        adapter=adapter,
        connection=connection,
        source_read_map=source_read_map,
        known_source_columns=known_source_columns,
    )
    return PlannerRelationsContext(
        model_locations=model_locations,
        seed_locations=seed_locations,
        function_locations=function_locations,
        source_map=source_map,
        source_read_map=source_read_map,
        python_source_read_map=python_source_read_map,
        source_warehouse_columns=get_semantic_source_columns(
            project=project,
            adapter=adapter,
            connection=connection,
            source_read_map=source_read_map,
            selected_keys=scope.selected_keys,
            columns=source_columns,
        ),
        star_exclude_keyword=adapter.star_exclude_keyword(),
        listed_source_names=listed_source_names,
    )


def _resolve_source_warehouse_columns(
    *,
    project: CompiledProjectView,
    adapter: BaseAdapter,
    connection: Any,
    source_read_map: dict[str, SourceEntry],
    known_source_columns: dict[str, tuple[ColumnInfo, ...]] | None,
) -> tuple[dict[str, tuple[ColumnInfo, ...]], frozenset[str]]:
    """Reuse already-gathered source columns for the read map or gather them once."""

    if known_source_columns is not None:
        known: dict[str, tuple[ColumnInfo, ...]] = {
            name: known_source_columns[name]
            for name in source_read_map
            if name in known_source_columns
        }
        return known, frozenset(known)
    return gather_source_inspection(
        project=project,
        adapter=adapter,
        connection=connection,
        source_entries=tuple(source_read_map.values()),
    )


def plan_model(
    *,
    model: CompiledModelView,
    snapshot: WarehouseSnapshot,
    adapter: BaseAdapter,
    context: ModelPlanContext,
    sql_analysis_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
    cursor_overrides: CursorOverridePair,
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
        external_sql_reference_resolver=external_sql_reference_resolver,
    )


def build_plan_entries(
    *,
    project: CompiledProjectView,
    adapter: BaseAdapter,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    relations: PlannerRelationsContext,
    resolved_actions: PlannerResolvedActions,
    cursor_overrides: CursorOverrides | None,
    full_refresh: bool,
    build_inputs: PlanEntryBuildInputs | None = None,
) -> PlannerModelEntryResults:
    """Build model plan entries from snapshot and per-model resolved actions."""

    inputs: PlanEntryBuildInputs = (
        build_inputs if build_inputs is not None else PlanEntryBuildInputs()
    )
    binding_diagnostics: tuple[CompilerDiagnostic, ...] = (
        *(
            diagnostic
            for diagnostic in project.diagnostics
            if diagnostic.is_error and diagnostic.resource_type != CompiledResourceType.SQL_TEST
        ),
        *source_binding_diagnostics(
            project=project,
            columns=relations.source_warehouse_columns,
            profile=adapter.expression_inference_profile(),
            selected_keys=scope.selected_keys,
        ),
    )
    binding_diagnostics = tuple(
        diagnostic for diagnostic in binding_diagnostics if diagnostic.is_error
    )
    if binding_diagnostics:
        raise PlannerInputError(
            "\n".join(
                f"error[{diagnostic.code}]: {diagnostic.message}\n"
                f"  --> {diagnostic.path}:{diagnostic.line or 1}:{diagnostic.column or 1}"
                for diagnostic in binding_diagnostics
            ),
            code=binding_diagnostics[0].code,
        )
    source_freshness_blocked_model_names: frozenset[str] = (
        inputs.source_freshness_blocked_model_names
    )
    external_blocked_model_names: frozenset[str] = inputs.external_blocked_model_names
    start_cursor_override: str | None = inputs.start_cursor_override
    end_cursor_override: str | None = inputs.end_cursor_override
    entries: list[ModelPlanEntry] = []
    warnings: list[PlanWarning] = []
    runtime_producer_names: frozenset[str] = runtime_cursor_producer_names(
        scope=scope,
        source_map=relations.source_map,
    )
    key: CompiledObjectKey
    for key in scope.execution_order:
        if key not in scope.selected_keys or key.name not in resolved_actions.models:
            continue
        model: CompiledModelView | None = scope.models_by_name.get(key.name)
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
                runtime_cursor_producer_names=runtime_producer_names,
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
            external_sql_reference_resolver=project.external_sql_reference_resolver,
            protect_full_refresh=key.name not in source_freshness_blocked_model_names
            and key.name not in external_blocked_model_names,
        )
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
        if entry.incremental_mode == IncrementalMode.MICROBATCH:
            entry = replace(
                entry,
                unaccounted_partition_policy=(
                    entry.unaccounted_partition_policy
                    or project.settings.microbatch_unaccounted_partition_policy
                ),
            )
            if entry.action != PlanAction.SKIP:
                entry, limit_warnings = apply_configured_microbatch_limits(
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
        note, guidance = microbatch_guidance()
        raise CompileInputError(f"{MICROBATCH_CONCURRENCY_MESSAGE}{names}; {note}", help=guidance)
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


def plan_model_from_change(
    *,
    model: CompiledModelView,
    snapshot: WarehouseSnapshot,
    adapter: BaseAdapter,
    context: ModelPlanContext,
    sql_analysis_enabled: bool,
    full_refresh: bool,
    cursor_overrides: CursorOverridePair,
    change_result: ChangeDetectionResult,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    protect_full_refresh: bool = True,
) -> tuple[ModelPlanEntry, tuple[PlanWarning, ...]]:
    """Build a model plan entry from a resolved change result."""

    start_cursor_override: str | None = cursor_overrides.start_cursor_override
    end_cursor_override: str | None = cursor_overrides.end_cursor_override
    backfill: BackfillResult = (
        BackfillResult(action=BackfillAction.FULL) if full_refresh else change_result.backfill
    )
    cursor_column: str | None = get_config_str(values=model.config.values, key="cursor")
    validate_source_cursor_input_columns(
        model=model,
        cursor_column=cursor_column,
        models_by_name=context.models_by_name,
        functions_by_name=context.functions_by_name,
        source_map=context.source_map,
        source_warehouse_columns=context.source_warehouse_columns,
    )

    action: PlanAction
    reason: PlanReason
    action, reason = resolve_model_plan_action(
        model=model,
        change_result=change_result,
        full_refresh=full_refresh,
    )
    materialization_type: MaterializationType = get_materialization_type(model)
    replaces_relation: bool = replaces_incremental_relation(
        materialization_type=materialization_type, action=action
    )
    full_rebuild_cause: str | None = (
        describe_full_rebuild_cause(change_result=change_result, full_refresh=full_refresh)
        if replaces_relation
        else None
    )
    if full_rebuild_cause is not None and protect_full_refresh and not full_refresh:
        check_full_rebuild_allowed(
            model=model, change_result=change_result, full_rebuild_cause=full_rebuild_cause
        )

    resolved_sql: str = resolve_model_sql(
        adapter=adapter,
        model=model,
        snapshot=snapshot,
        context=context,
        backfill=backfill,
        full_refresh=full_refresh,
        cursor_overrides=cursor_overrides,
        external_sql_reference_resolver=external_sql_reference_resolver,
        replaces_relation=replaces_relation,
        full_rebuild_cause=full_rebuild_cause,
    )

    pre_hooks, post_hooks = resolve_model_hook_entries(
        model=model,
        adapter=adapter,
        context=context,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    effective_future_cursor_config, effective_start_cursor_config = _resolve_cursor_safety_configs(
        model=model, context=context
    )
    validate_capped_watermark_inputs(
        model=model,
        models_by_name=context.models_by_name,
        functions_by_name=context.functions_by_name,
    )
    cursor_input_relations: tuple[CursorInputRelation, ...] = build_cursor_input_relations(
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
    runtime_owned_cursor_bounds: bool = any(
        relation.is_runtime_owned for relation in cursor_input_relations
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

    empty_cursor_inputs: tuple[str, ...]
    waiting_on_empty_inputs: bool
    empty_cursor_inputs, waiting_on_empty_inputs = _resolve_empty_cursor_inputs(
        model=model,
        snapshot=snapshot,
        full_refresh=full_refresh,
        runtime_owned_cursor_bounds=runtime_owned_cursor_bounds,
        cursor_overrides=cursor_overrides,
    )

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
            replaces_relation=replaces_relation,
        ),
    )

    entry: ModelPlanEntry
    warnings: tuple[PlanWarning, ...]
    entry, warnings = assemble_model_plan_entry(
        model=model,
        adapter=adapter,
        snapshot=snapshot,
        change_result=change_result,
        action=action,
        reason=reason,
        materialization_type=materialization_type,
        resolved_sql=resolved_sql,
        sql_analysis_enabled=sql_analysis_enabled,
        pre_hooks=pre_hooks,
        post_hooks=post_hooks,
        cursor_column=cursor_column,
        cursor_input_relations=cursor_input_relations,
        runtime_owned_cursor_bounds=runtime_owned_cursor_bounds,
        cursor_bounds=cursor_bounds,
        microbatch_range=microbatch_range,
        empty_cursor_inputs=empty_cursor_inputs,
        waiting_on_empty_inputs=waiting_on_empty_inputs,
        backfill=backfill,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        future_cursor_config=effective_future_cursor_config,
        start_cursor_config=effective_start_cursor_config,
        invocation_time=context.invocation_time,
    )
    return entry, _append_cursor_safety_warnings(
        warnings=warnings,
        model_name=model.name,
        bounds=microbatch_range or cursor_bounds,
    )


def resolve_cursor_overrides(
    *,
    model: CompiledModelView,
    cursor_overrides: CursorOverrides | None,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
) -> tuple[str | None, str | None]:
    """Resolve typed cursor overrides to generic start/end for one model."""

    cursor_type: str | None = get_config_str(values=model.config.values, key="cursor_type")
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

    cursor_start: str | None = get_config_cursor_bound(
        values=model.config.values, key="cursor_start"
    )
    cursor_end: str | None = get_config_cursor_bound(values=model.config.values, key="cursor_end")
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


def _resolve_cursor_safety_configs(
    *, model: CompiledModelView, context: ModelPlanContext
) -> tuple[FutureCursorsConfig | None, StartCursorsConfig | None]:
    return (
        resolve_future_cursor_config(model=model, project_config=context.future_cursor_config),
        resolve_start_cursor_config(model=model, project_config=context.start_cursor_config),
    )


def _compute_microbatch_range(
    *, model: CompiledModelView, inputs: _MicrobatchRangeInputs
) -> CursorBounds | None:
    """Compute the real overall cursor range for microbatch batch splitting."""

    materialized: str | None = get_config_str(values=model.config.values, key="materialized")
    if materialized != MaterializationType.INCREMENTAL:
        return None
    incremental_mode: str | None = get_config_str(
        values=model.config.values, key="incremental_mode"
    )
    if incremental_mode != IncrementalMode.MICROBATCH:
        return None
    cursor_column: str | None = get_config_str(values=model.config.values, key="cursor")
    if cursor_column is None:
        return None
    bounded_override: CursorBounds | None = resolve_bounded_cursor_override(
        start_cursor_override=inputs.start_cursor_override,
        end_cursor_override=inputs.end_cursor_override,
        cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
        cursor_grain=get_config_str(values=model.config.values, key="cursor_grain"),
    )
    if bounded_override is not None:
        return _clamp_cursor_end(bounds=bounded_override, model=model)
    if (
        get_config_str(values=model.config.values, key="microbatch_strategy")
        == MicrobatchStrategy.ROLLING_WINDOW
    ):
        rolling_bounds: CursorBounds | None = _rolling_window_bounds(
            model=model, invocation_time=inputs.invocation_time
        )
        if inputs.full_refresh and rolling_bounds is not None:
            cursor_start: str | None = get_config_cursor_bound(
                values=model.config.values, key="cursor_start"
            )
            if cursor_start is not None:
                rolling_bounds = replace(rolling_bounds, start=cursor_start)
        return rolling_bounds
    if inputs.runtime_owned_cursor_bounds:
        return None
    cursor_snapshot: ModelCursorSnapshot | None = inputs.snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return None
    if inputs.replaces_relation and not inputs.full_refresh:
        cursor_snapshot = without_destination_cursor(cursor_snapshot=cursor_snapshot)

    cursor_type: str | None = get_config_str(values=model.config.values, key="cursor_type")
    downstream_grain: str | None = get_config_str(values=model.config.values, key="cursor_grain")
    effective_grain: str | None = resolve_effective_timestamp_grain(
        cursor_type=cursor_type,
        downstream_grain=downstream_grain,
        microbatch_strategy=get_config_str(values=model.config.values, key="microbatch_strategy"),
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
    cursor_start: str | None = get_config_cursor_bound(
        values=model.config.values, key="cursor_start"
    )
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
            incremental_strategy=get_config_str(
                values=model.config.values, key="incremental_strategy"
            ),
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


def _compute_plan_cursor_bounds(
    *,
    model: CompiledModelView,
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

    materialized: str | None = get_config_str(values=model.config.values, key="materialized")
    cursor_column: str | None = get_config_str(values=model.config.values, key="cursor")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None
    bounded_override: CursorBounds | None = resolve_bounded_cursor_override(
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        cursor_type=get_config_str(values=model.config.values, key="cursor_type"),
        cursor_grain=get_config_str(values=model.config.values, key="cursor_grain"),
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
    if backfill.action == BackfillAction.FULL:
        cursor_snapshot = without_destination_cursor(cursor_snapshot=cursor_snapshot)

    lookback: str | None = get_config_str(values=model.config.values, key="lookback")
    cursor_start: str | None = get_config_cursor_bound(
        values=model.config.values, key="cursor_start"
    )
    incremental_mode: str | None = get_config_str(
        values=model.config.values, key="incremental_mode"
    )
    is_microbatch: bool = incremental_mode == IncrementalMode.MICROBATCH

    backfill_duration: str | None = None
    if backfill.action == BackfillAction.BOUNDED:
        backfill_duration = backfill.duration

    cursor_type: str | None = get_config_str(values=model.config.values, key="cursor_type")
    cursor_grain: str | None = get_config_str(values=model.config.values, key="cursor_grain")
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
            incremental_strategy=get_config_str(
                values=model.config.values, key="incremental_strategy"
            ),
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


def _resolve_empty_cursor_inputs(
    *,
    model: CompiledModelView,
    snapshot: WarehouseSnapshot,
    full_refresh: bool,
    runtime_owned_cursor_bounds: bool,
    cursor_overrides: CursorOverridePair,
) -> tuple[tuple[str, ...], bool]:
    """Return empty inputs that leave a planner-owned window empty, and whether others have rows."""

    if (
        full_refresh
        or runtime_owned_cursor_bounds
        or get_config_str(values=model.config.values, key="materialized")
        != MaterializationType.INCREMENTAL
        or get_config_str(values=model.config.values, key="cursor") is None
        or get_config_str(values=model.config.values, key="microbatch_strategy")
        == MicrobatchStrategy.ROLLING_WINDOW
        or (
            cursor_overrides.start_cursor_override is not None
            and cursor_overrides.end_cursor_override is not None
        )
    ):
        return (), False
    cursor_snapshot: ModelCursorSnapshot | None = snapshot.cursor_snapshots.get(model.name)
    if cursor_snapshot is None:
        return (), False
    decision: EmptyCursorInputDecision = cursor_inputs_without_rows(cursor_snapshot=cursor_snapshot)
    return decision.input_names, decision.waiting_on_empty_inputs


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


def _selected_audit_relation_keys(
    *,
    project: CompiledProjectView,
    selected_keys: frozenset[CompiledObjectKey],
) -> frozenset[CompiledObjectKey]:
    """Return relation keys needed to render selected audits without selecting those relations."""

    relation_keys: set[CompiledObjectKey] = set()
    audit: CompiledAuditView
    for audit in project.audits:
        if audit_is_selected(audit=audit, selected_keys=selected_keys):
            relation_keys.update(audit.scope_deps)
    return frozenset(relation_keys)


def build_model_materializations(
    model_entries: tuple[ModelPlanEntry, ...],
) -> dict[str, str]:
    """Build a name-to-materialization-type lookup from planned model entries."""

    return {entry.name: entry.materialization_type for entry in model_entries}


def _rolling_window_bounds(
    *, model: CompiledModelView, invocation_time: datetime | None
) -> CursorBounds | None:
    grain: str | None = get_config_str(values=model.config.values, key="cursor_grain")
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
    cursor_start: str | None = get_config_cursor_bound(
        values=model.config.values, key="cursor_start"
    )
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


def _clamp_cursor_end(
    *, bounds: CursorBounds | None, model: CompiledModelView
) -> CursorBounds | None:
    cursor_end: str | None = get_config_cursor_bound(values=model.config.values, key="cursor_end")
    cursor_type: str | None = get_config_str(values=model.config.values, key="cursor_type")
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
