"""Single-model table execution lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import AuditPlanEntry, CursorBounds, ModelPlanEntry
from sqlbuild.compiler.planner.types import RelationReuseKind
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.run.helpers.execution.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.execution.promotion import promote_relation_to_destination
from sqlbuild.executor.run.helpers.execution.results import (
    build_failed_result,
    build_skipped_result,
)
from sqlbuild.executor.run.helpers.materializations.custom import (
    execute_custom_entry as execute_custom_entry,
)
from sqlbuild.executor.run.helpers.materializations.incremental import (
    execute_incremental_entry as execute_incremental_entry,
)
from sqlbuild.executor.run.helpers.materializations.microbatch import (
    execute_microbatch_entry as execute_microbatch_entry,
)
from sqlbuild.executor.run.helpers.materializations.snapshot import (
    execute_snapshot_entry as execute_snapshot_entry,
)
from sqlbuild.executor.run.helpers.materializations.view import (
    execute_view_entry as execute_view_entry,
)
from sqlbuild.executor.run.helpers.execution.final_audits import run_final_model_audits
from sqlbuild.executor.run.helpers.reuse.core import (
    create_relation_from_reuse_plan,
)
from sqlbuild.executor.run.helpers.reuse.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.validation.contracts import validate_runtime_contract
from sqlbuild.executor.run.helpers.validation.cursor_bounds import (
    has_model_backed_cursor_inputs,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run.helpers.validation.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import (
    FinalAuditRun,
    HookExecutionResult,
    ModelExecutionResult,
)
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.helpers.diagnostics.logging import diagnostics_context
from sqlbuild.shared.helpers.identity.naming import (
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
    python_identity_recorder: PythonIdentityRecorder | None = None,
) -> ModelExecutionResult:
    """Execute one table model through its full materialization lifecycle."""

    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_table: str = entry.destination.name
    target_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
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
        try:
            runtime_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
                adapter=adapter,
                connection=connection,
                target_relation=target_qualified,
                target_database=target_database,
                target_schema=target_schema,
                target_name=target_table,
                cursor_column=entry.cursor_column,
                cursor_type=entry.cursor_type,
                cursor_grain=entry.cursor_grain,
                cursor_start=entry.cursor_start,
                cursor_input_relations=entry.cursor_input_relations,
            )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"failed to resolve runtime cursor bounds: {exc}",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
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
            pre_hook_skipped: bool = execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.pre_hooks,
                phase=HookPhase.PRE_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                target=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
                python_identity_recorder=python_identity_recorder,
            )
        if pre_hook_skipped:
            return build_skipped_result(
                entry=entry,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
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
            hook_functions=hook_functions,
            effective_target_name=effective_target_name,
            effective_vars=effective_vars,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
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
        hook_functions=hook_functions,
        effective_target_name=effective_target_name,
        effective_vars=effective_vars,
        providers=providers,
        python_identity_recorder=python_identity_recorder,
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
    hook_functions: tuple[DiscoveredHookFunction, ...],
    effective_target_name: str | None,
    effective_vars: Mapping[str, object] | None,
    providers: ProviderContainer | None,
    python_identity_recorder: PythonIdentityRecorder | None,
) -> ModelExecutionResult:
    """Staged table lifecycle: CTAS staging, type enforce, audit, promote."""

    reuse_origin_fingerprint: Fingerprint | None = None
    try:
        with diagnostics_context(
            sqlbuild_phase="materialize", sqlbuild_action_name="create_staging"
        ):
            adapter.drop(
                connection,
                destination=staging_qualified,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
            if (
                entry.relation_reuse is not None
                and entry.relation_reuse.kind == RelationReuseKind.COMPLETE_RELATION_REUSE
            ):
                reuse_origin_fingerprint = create_relation_from_reuse_plan(
                    adapter=adapter,
                    connection=connection,
                    model_name=entry.name,
                    expected_version_hash=entry.fingerprint_version_hash,
                    relation_reuse=entry.relation_reuse,
                    destination_relation=staging_qualified,
                    statement_recorder=statement_recorder,
                )
            else:
                adapter.create_table_as(
                    connection,
                    destination=staging_qualified,
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

    final_audit_run: FinalAuditRun = run_final_model_audits(
        relation_overrides={entry.name: staging_qualified},
        model_audits=model_audits,
        reuse_origin_fingerprint=reuse_origin_fingerprint,
        adapter=adapter,
        connection=connection,
        model_locations=model_locations,
        seed_locations=seed_locations,
        source_map=source_map,
    )
    audit_results.extend(final_audit_run.results)

    if final_audit_run.has_error:
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
            _ = promote_relation_to_destination(
                adapter=adapter,
                connection=connection,
                origin_relation=staging_qualified,
                destination_relation=target_qualified,
                destination_database=target_database,
                destination_schema=target_schema,
                destination_name=target_table,
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
            post_hook_skipped: bool = execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hooks,
                phase=HookPhase.POST_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                target=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
                python_identity_recorder=python_identity_recorder,
            )
        if post_hook_skipped:
            return build_skipped_result(
                entry=entry,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                promoted_relation=target_qualified,
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

    fingerprint_warnings: tuple[str, ...] = try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        model_audits=model_audits,
        audit_results=tuple(audit_results),
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings) + fingerprint_warnings,
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
    hook_functions: tuple[DiscoveredHookFunction, ...],
    effective_target_name: str | None,
    effective_vars: Mapping[str, object] | None,
    providers: ProviderContainer | None,
    python_identity_recorder: PythonIdentityRecorder | None,
) -> ModelExecutionResult:
    """Direct table lifecycle: CTAS target, audit after, no staging."""

    reuse_origin_fingerprint: Fingerprint | None = None
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
            if (
                entry.relation_reuse is not None
                and entry.relation_reuse.kind == RelationReuseKind.COMPLETE_RELATION_REUSE
            ):
                adapter.drop(
                    connection,
                    destination=target_qualified,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
                reuse_origin_fingerprint = create_relation_from_reuse_plan(
                    adapter=adapter,
                    connection=connection,
                    model_name=entry.name,
                    expected_version_hash=entry.fingerprint_version_hash,
                    relation_reuse=entry.relation_reuse,
                    destination_relation=target_qualified,
                    statement_recorder=statement_recorder,
                )
            else:
                adapter.create_table_as(
                    connection,
                    destination=target_qualified,
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

    direct_audit_run: FinalAuditRun = run_final_model_audits(
        relation_overrides=None,
        model_audits=model_audits,
        reuse_origin_fingerprint=reuse_origin_fingerprint,
        adapter=adapter,
        connection=connection,
        model_locations=model_locations,
        seed_locations=seed_locations,
        source_map=source_map,
    )
    audit_results.extend(direct_audit_run.results)

    if direct_audit_run.has_error:
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
            post_hook_skipped: bool = execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hooks,
                phase=HookPhase.POST_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                target=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
                python_identity_recorder=python_identity_recorder,
            )
        if post_hook_skipped:
            return build_skipped_result(
                entry=entry,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                promoted_relation=target_qualified,
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

    fingerprint_warnings: tuple[str, ...] = try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        model_audits=model_audits,
        audit_results=tuple(audit_results),
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings) + fingerprint_warnings,
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )
