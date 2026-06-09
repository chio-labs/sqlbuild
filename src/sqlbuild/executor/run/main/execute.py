"""Single-model table execution lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.adapter.shared.types import PromotionStrategy, TablePromotionMode
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, CursorBounds, ModelPlanEntry
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.contracts import validate_runtime_contract
from sqlbuild.executor.run.helpers.cursor_bounds import (
    has_model_backed_cursor_inputs,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run.helpers.custom import (
    execute_custom_entry as execute_custom_entry,
)
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.incremental import (
    execute_incremental_entry as execute_incremental_entry,
)
from sqlbuild.executor.run.helpers.microbatch import (
    execute_microbatch_entry as execute_microbatch_entry,
)
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.helpers.reuse import create_relation_from_reuse_origin
from sqlbuild.executor.run.helpers.snapshot import (
    execute_snapshot_entry as execute_snapshot_entry,
)
from sqlbuild.executor.run.helpers.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.helpers.view import (
    execute_view_entry as execute_view_entry,
)
from sqlbuild.executor.run.models import HookExecutionResult, ModelExecutionResult
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context
from sqlbuild.shared.helpers.naming import (
    resolve_qualified_name_parts,
    resolve_relation_location_qualified_name,
)
from sqlbuild.spec.models.source import SourceEntry


def execute_table_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    promotion_mode: TablePromotionMode,
    run_id: str,
    query_change_tracking: bool,
    hook_functions: tuple[DiscoveredHookFunction, ...] = (),
    effective_target_name: str | None = None,
    effective_vars: Mapping[str, object] | None = None,
    providers: ProviderContainer | None = None,
) -> ModelExecutionResult:
    """Execute one table model through its full materialization lifecycle."""

    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_table: str = entry.destination.name
    target_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    reuse_origin_relation: str | None = (
        resolve_relation_location_qualified_name(
            adapter=adapter,
            location=entry.reuse_origin,
        )
        if entry.reuse_origin is not None
        else None
    )
    staging_table: str = f"{target_table}__staging"
    staging_qualified: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=target_database,
        schema=target_schema,
        name=staging_table,
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    hook_results: list[HookExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()
    runtime_owned_cursor_bounds: bool = has_model_backed_cursor_inputs(entry.cursor_input_relations)
    resolved_sql: str = entry.resolved_sql

    if runtime_owned_cursor_bounds:
        if entry.cursor_column is None:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error="runtime-owned cursor resolution requires cursor_column",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
            )
        runtime_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
            adapter=adapter,
            connection=connection,
            target_relation=target_qualified,
            cursor_column=entry.cursor_column,
            cursor_type=entry.cursor_type,
            cursor_grain=entry.cursor_grain,
            cursor_start=entry.cursor_start,
            cursor_input_relations=entry.cursor_input_relations,
        )
        if runtime_bounds is None:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"runtime cursor bounds could not be resolved for '{entry.name}'",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )
        resolved_sql = substitute_cursor_sentinels(sql=entry.resolved_sql, bounds=runtime_bounds)

    try:
        adapter.ensure_schema(
            connection,
            database=target_database,
            schema=target_schema,
            statement_recorder=statement_recorder,
        )
        statement_recorder.record_many(
            render_hooks(hooks=entry.pre_hooks, phase=HookPhase.PRE_HOOKS)
        )
        with diagnostics_context(sqlbuild_phase="pre_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.pre_hooks,
                phase=HookPhase.PRE_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                environment=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PRE_HOOK,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    if promotion_mode == TablePromotionMode.STAGED:
        return _staged_lifecycle(
            entry=entry,
            adapter=adapter,
            connection=connection,
            target_qualified=target_qualified,
            target_database=target_database,
            target_schema=target_schema,
            target_table=target_table,
            staging_qualified=staging_qualified,
            staging_table=staging_table,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            model_audits=model_audits,
            declared_columns=declared_columns,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
            resolved_sql=resolved_sql,
            reuse_origin_relation=reuse_origin_relation,
            hook_functions=hook_functions,
            effective_target_name=effective_target_name,
            effective_vars=effective_vars,
            providers=providers,
        )

    if entry.contract_enforced:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CONTRACT,
            error=ExecutorInputError(
                f"model '{entry.name}': contract enforced requires staged table promotion; "
                "direct table promotion cannot validate runtime output before target mutation",
                code="K011",
            ),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    return _direct_lifecycle(
        entry=entry,
        adapter=adapter,
        connection=connection,
        target_qualified=target_qualified,
        model_locations=model_locations,
        seed_locations=seed_locations,
        source_map=source_map,
        model_audits=model_audits,
        declared_columns=declared_columns,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        warnings=warnings,
        audit_results=audit_results,
        statement_recorder=statement_recorder,
        hook_results=hook_results,
        resolved_sql=resolved_sql,
        reuse_origin_relation=reuse_origin_relation,
        hook_functions=hook_functions,
        effective_target_name=effective_target_name,
        effective_vars=effective_vars,
        providers=providers,
    )


def _staged_lifecycle(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    target_qualified: str,
    target_database: str | None,
    target_schema: str | None,
    target_table: str,
    staging_qualified: str,
    staging_table: str,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    run_id: str,
    query_change_tracking: bool,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
    hook_results: list[HookExecutionResult],
    resolved_sql: str,
    reuse_origin_relation: str | None,
    hook_functions: tuple[DiscoveredHookFunction, ...],
    effective_target_name: str | None,
    effective_vars: Mapping[str, object] | None,
    providers: ProviderContainer | None,
) -> ModelExecutionResult:
    """Staged table lifecycle: CTAS staging, type enforce, audit, promote."""

    try:
        with diagnostics_context(
            sqlbuild_phase="materialize", sqlbuild_action_name="create_staging"
        ):
            adapter.drop(
                connection,
                target=staging_qualified,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
            if reuse_origin_relation is not None:
                create_relation_from_reuse_origin(
                    adapter=adapter,
                    connection=connection,
                    origin_relation=reuse_origin_relation,
                    destination_relation=staging_qualified,
                    hard_copy=entry.reuse_hard_copy,
                    statement_recorder=statement_recorder,
                )
            else:
                adapter.create_table_as(
                    connection,
                    target=staging_qualified,
                    sql=resolved_sql,
                    statement_recorder=statement_recorder,
                )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    if entry.type_enforcement and declared_columns:
        try:
            with diagnostics_context(
                sqlbuild_phase="type_enforcement", sqlbuild_action_name="rebuild_staging"
            ):
                enforce_types_staged(
                    adapter=adapter,
                    connection=connection,
                    staging_qualified=staging_qualified,
                    staging_database=target_database,
                    staging_schema=target_schema,
                    staging_table=staging_table,
                    declared_columns=declared_columns,
                    statement_recorder=statement_recorder,
                )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.TYPE_ENFORCEMENT,
                error=str(exc),
                staging_relation=staging_qualified,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

    try:
        with diagnostics_context(
            sqlbuild_phase="contract", sqlbuild_action_name="validate_staging"
        ):
            staging_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                connection,
                database=target_database,
                schema=target_schema,
                name=staging_table,
            )
            validate_runtime_contract(
                entry=entry,
                actual_columns=staging_columns,
                dialect=adapter.sql_analysis_dialect_name,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CONTRACT,
            error=exc,
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    overrides: dict[str, str] = {entry.name: staging_qualified}
    audit_error: bool = False
    audit: AuditPlanEntry
    for audit in model_audits:
        result: AuditExecutionResult = execute_audit(
            audit=audit,
            adapter=adapter,
            connection=connection,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            relation_overrides=overrides,
            run_scope_phase=AuditRunScope.FINAL,
        )
        audit_results.append(result)
        if result.outcome == AuditOutcome.ERROR:
            audit_error = True

    if audit_error:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{entry.name}' failed before replacing target table "
                "with severity level: error"
            ),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try:
        with diagnostics_context(sqlbuild_phase="promote", sqlbuild_action_name="check_existing"):
            existing: bool = adapter.relation_exists(
                connection,
                database=target_database,
                schema=target_schema,
                name=target_table,
            )
        promotion_strategy: PromotionStrategy = adapter.default_promotion_strategy()
        if existing and promotion_strategy == PromotionStrategy.ATOMIC_SWAP:
            with diagnostics_context(sqlbuild_phase="promote", sqlbuild_action_name="atomic_swap"):
                adapter.swap(
                    connection,
                    left=target_qualified,
                    right=staging_qualified,
                    statement_recorder=statement_recorder,
                )
                adapter.drop(
                    connection,
                    target=staging_qualified,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
        elif existing and promotion_strategy == PromotionStrategy.ATOMIC_REPLACE:
            with diagnostics_context(
                sqlbuild_phase="promote",
                sqlbuild_action_name="atomic_replace",
            ):
                adapter.replace_table_from_relation(
                    connection,
                    destination=target_qualified,
                    origin=staging_qualified,
                    statement_recorder=statement_recorder,
                )
                adapter.drop(
                    connection,
                    target=staging_qualified,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
        elif existing:
            raise ExecutorInputError(f"Unsupported promotion strategy: {promotion_strategy}")
        else:
            with diagnostics_context(sqlbuild_phase="promote", sqlbuild_action_name="rename"):
                adapter.rename(
                    connection,
                    origin=staging_qualified,
                    destination=target_qualified,
                    statement_recorder=statement_recorder,
                )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PROMOTION,
            error=str(exc),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try:
        statement_recorder.record_many(
            render_hooks(hooks=entry.post_hooks, phase=HookPhase.POST_HOOKS)
        )
        with diagnostics_context(sqlbuild_phase="post_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hooks,
                phase=HookPhase.POST_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                environment=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.POST_HOOK,
            error=str(exc),
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        warnings=warnings,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )


def _direct_lifecycle(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    target_qualified: str,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    run_id: str,
    query_change_tracking: bool,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
    hook_results: list[HookExecutionResult],
    resolved_sql: str,
    reuse_origin_relation: str | None,
    hook_functions: tuple[DiscoveredHookFunction, ...],
    effective_target_name: str | None,
    effective_vars: Mapping[str, object] | None,
    providers: ProviderContainer | None,
) -> ModelExecutionResult:
    """Direct table lifecycle: CTAS target, audit after, no staging."""

    if entry.type_enforcement and declared_columns:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.TYPE_ENFORCEMENT,
            error=(
                f"model '{entry.name}': type enforcement requires staged promotion mode "
                f"for runtime column inspection; set table_promotion_mode: staged in "
                f"sqlbuild_project.toml settings"
            ),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try:
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="create_table"):
            if reuse_origin_relation is not None:
                adapter.drop(
                    connection,
                    target=target_qualified,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
                create_relation_from_reuse_origin(
                    adapter=adapter,
                    connection=connection,
                    origin_relation=reuse_origin_relation,
                    destination_relation=target_qualified,
                    hard_copy=entry.reuse_hard_copy,
                    statement_recorder=statement_recorder,
                )
            else:
                adapter.create_table_as(
                    connection,
                    target=target_qualified,
                    sql=resolved_sql,
                    statement_recorder=statement_recorder,
                )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    audit_error: bool = False
    audit: AuditPlanEntry
    for audit in model_audits:
        result: AuditExecutionResult = execute_audit(
            audit=audit,
            adapter=adapter,
            connection=connection,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            relation_overrides=None,
            run_scope_phase=AuditRunScope.FINAL,
        )
        audit_results.append(result)
        if result.outcome == AuditOutcome.ERROR:
            audit_error = True

    if audit_error:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{entry.name}' failed after target table was replaced "
                "with severity level: error"
            ),
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try:
        statement_recorder.record_many(
            render_hooks(hooks=entry.post_hooks, phase=HookPhase.POST_HOOKS)
        )
        with diagnostics_context(sqlbuild_phase="post_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hooks,
                phase=HookPhase.POST_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                environment=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.POST_HOOK,
            error=str(exc),
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        warnings=warnings,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )
