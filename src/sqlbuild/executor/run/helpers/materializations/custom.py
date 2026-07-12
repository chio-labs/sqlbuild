"""Custom materialization execution lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry, SchemaFinding
from sqlbuild.compiler.planner.types import PlanReason, RelationReuseKind
from sqlbuild.diagnostics.helpers.logging import diagnostics_context
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import (
    MaterializationContext,
    MaterializationResult,
    PrepareVersionContext,
)
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.run.helpers.execution.final_audits import run_final_scope_audits
from sqlbuild.executor.run.helpers.execution.hooks import execute_hooks
from sqlbuild.executor.run.helpers.execution.results import (
    build_failed_result,
    build_skipped_result,
)
from sqlbuild.executor.run.helpers.reuse.core import read_current_reuse_origin_fingerprint
from sqlbuild.executor.run.helpers.reuse.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.models import (
    FinalAuditRun,
    HookExecutionResult,
    HookRunContext,
    ModelExecutionResult,
    ModelMaterializationContext,
)
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import (
    ProviderContainer,
    _empty_provider_container,
    invoke_with_providers,
)
from sqlbuild.shared.helpers.identity.naming import resolve_relation_location_qualified_name
from sqlbuild.spec.models.source import SourceEntry


def execute_custom_entry(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    materialize_fn: Callable[[MaterializationContext], MaterializationResult],
    target: str,
    effective_vars: dict[str, object],
    existing_relation: RelationInfo | None,
    prepare_version_fn: Callable[[PrepareVersionContext], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ModelExecutionResult:
    """Execute one model through the custom materialization lifecycle."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    model_locations: dict[str, CompiledRelationLocation] = context.model_locations
    seed_locations: dict[str, CompiledRelationLocation] = context.seed_locations
    source_map: dict[str, SourceEntry] = context.source_map
    model_audits: tuple[AuditPlanEntry, ...] = context.model_audits
    run_id: str = context.run_id
    query_change_tracking: bool = context.query_change_tracking
    hook_functions: tuple[DiscoveredHookFunction, ...] = context.hook_functions
    effective_target_name: str | None = context.effective_target_name
    providers: ProviderContainer | None = context.providers
    python_identity_recorder: PythonIdentityRecorder | None = context.python_identity_recorder
    destination_database: str | None = entry.destination.database
    destination_schema: str | None = entry.destination.schema
    destination_name: str = entry.destination.name
    destination_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    hook_results: list[HookExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()

    adapter.ensure_schema(
        connection=connection,
        database=destination_database,
        schema=destination_schema,
        statement_recorder=statement_recorder,
    )

    try:
        with diagnostics_context(sqlbuild_phase="pre_hook", sqlbuild_action_name="run"):
            pre_hook_skipped: bool = execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.pre_hooks,
                phase=HookPhase.PRE_HOOKS,
                hook_functions=hook_functions,
                hook_results=hook_results,
                hook_run=HookRunContext(
                    model_name=entry.name,
                    destination=entry.destination,
                    run_id=run_id,
                    target=effective_target_name,
                    effective_vars=effective_vars,
                    statement_recorder=statement_recorder,
                    providers=providers,
                    python_identity_recorder=python_identity_recorder,
                ),
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

    config_dict: dict[str, Any] = dict(entry.custom_config)
    placeholders_dict: dict[str, str] = dict(entry.custom_placeholders)
    context_providers: ProviderContainer = providers or _empty_provider_container()

    if (
        entry.relation_reuse is not None
        and entry.relation_reuse.kind == RelationReuseKind.SEEDED_RELATION_REUSE
    ):
        if prepare_version_fn is None:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
                error=(
                    f"custom materialization '{entry.custom_materialization_name}' cannot use "
                    "baseline reuse without prepare_version(ctx)"
                ),
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
            )
        try:
            read_current_reuse_origin_fingerprint(
                adapter=adapter,
                connection=connection,
                model_name=entry.name,
                expected_version_hash=entry.fingerprint_version_hash,
                reuse_from_target_name=entry.relation_reuse.reuse_from_target_name,
                reuse_origin_fingerprint_database=entry.relation_reuse.fingerprint_database,
                reuse_origin_fingerprint_schema=entry.relation_reuse.fingerprint_schema,
            )
            with diagnostics_context(
                sqlbuild_phase="prepare_version", sqlbuild_action_name="custom"
            ):
                invoke_with_providers(
                    function=prepare_version_fn,
                    context=PrepareVersionContext(
                        adapter=adapter,
                        connection=connection,
                        origin_relation=resolve_relation_location_qualified_name(
                            adapter=adapter,
                            location=entry.relation_reuse.origin,
                        ),
                        destination=destination_qualified,
                        destination_database=destination_database,
                        destination_schema=destination_schema,
                        destination_name=destination_name,
                        config=config_dict,
                        placeholders=placeholders_dict,
                        run_id=run_id,
                        environment=effective_target_name or target,
                        vars=effective_vars,
                        unique_key=entry.unique_key,
                        declared_columns=declared_columns,
                        statement_recorder=statement_recorder,
                    ),
                    providers=providers,
                )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
                error=str(exc),
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
            )

    run_audits_fn: Callable[[str], tuple[AuditExecutionResult, ...]] = _build_run_audits(
        model_audits=model_audits,
        adapter=adapter,
        connection=connection,
        model_locations=model_locations,
        seed_locations=seed_locations,
        source_map=source_map,
        model_name=entry.name,
    )

    is_first_run: bool = existing_relation is None
    is_full_refresh: bool = entry.reason == PlanReason.FULL_REFRESH
    query_changed: bool = entry.reason == PlanReason.QUERY_CHANGED
    schema_findings: tuple[SchemaFinding, ...] = entry.schema_findings

    ctx: MaterializationContext = MaterializationContext(
        adapter=adapter,
        connection=connection,
        destination=destination_qualified,
        destination_database=destination_database,
        destination_schema=destination_schema,
        destination_name=destination_name,
        sql=entry.resolved_sql,
        config=config_dict,
        placeholders=placeholders_dict,
        existing_relation=existing_relation,
        run_id=run_id,
        build_target=target,
        vars=effective_vars,
        unique_key=entry.unique_key,
        declared_columns=declared_columns,
        is_first_run=is_first_run,
        is_full_refresh=is_full_refresh,
        query_changed=query_changed,
        schema_findings=schema_findings,
        run_audits=run_audits_fn,
        on_progress=on_progress,
        logger=logging.getLogger(f"sqlbuild.materialization.{entry.name}"),
        statement_recorder=statement_recorder,
        providers=context_providers,
    )

    try:
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="custom"):
            result: object = invoke_with_providers(
                function=materialize_fn,
                context=ctx,
                providers=providers,
            )
            materialization_result: MaterializationResult = cast(MaterializationResult, result)
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    if materialization_result.failed:
        user_audit_results: list[AuditExecutionResult] = (
            list(materialization_result.audit_results)
            if materialization_result.audit_results is not None
            else []
        )
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
            error=materialization_result.error or "custom materialization reported failure",
            warnings=warnings,
            audit_results=user_audit_results,
            statement_recorder=statement_recorder,
        )

    if materialization_result.audit_results is not None:
        audit_results.extend(materialization_result.audit_results)
    else:
        final_audit_run: FinalAuditRun = run_final_scope_audits(context=context)
        audit_results.extend(final_audit_run.results)

        if final_audit_run.has_error:
            _cleanup_relations(
                adapter=adapter,
                connection=connection,
                relations=materialization_result.cleanup_relations,
                keep=True,
                statement_recorder=statement_recorder,
            )
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.AUDIT,
                error=(
                    f"final audit for '{entry.name}' failed after materialization "
                    "with severity level: error"
                ),
                promoted_relation=materialization_result.relation,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

    try:
        with diagnostics_context(sqlbuild_phase="post_hook", sqlbuild_action_name="run"):
            post_hook_skipped: bool = execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hooks,
                phase=HookPhase.POST_HOOKS,
                hook_functions=hook_functions,
                hook_results=hook_results,
                hook_run=HookRunContext(
                    model_name=entry.name,
                    destination=entry.destination,
                    run_id=run_id,
                    target=effective_target_name,
                    effective_vars=effective_vars,
                    statement_recorder=statement_recorder,
                    providers=providers,
                    python_identity_recorder=python_identity_recorder,
                ),
            )
        if post_hook_skipped:
            _cleanup_relations(
                adapter=adapter,
                connection=connection,
                relations=materialization_result.cleanup_relations,
                keep=False,
                statement_recorder=statement_recorder,
            )
            return build_skipped_result(
                entry=entry,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                promoted_relation=materialization_result.relation,
            )
    except Exception as exc:
        _cleanup_relations(
            adapter=adapter,
            connection=connection,
            relations=materialization_result.cleanup_relations,
            keep=True,
            statement_recorder=statement_recorder,
        )
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.POST_HOOK,
            error=str(exc),
            promoted_relation=materialization_result.relation,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    warnings.extend(
        try_write_fingerprint(
            entry=entry,
            adapter=adapter,
            connection=connection,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            model_audits=model_audits,
            audit_results=tuple(audit_results),
        )
    )

    _cleanup_relations(
        adapter=adapter,
        connection=connection,
        relations=materialization_result.cleanup_relations,
        keep=False,
        statement_recorder=statement_recorder,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=materialization_result.relation,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )


def _build_run_audits(
    *,
    model_audits: tuple[AuditPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    model_name: str,
) -> Callable[[str], tuple[AuditExecutionResult, ...]]:
    """Build the run_audits callable for the materialization context."""

    def run_audits(against: str) -> tuple[AuditExecutionResult, ...]:
        overrides: dict[str, str] = {model_name: against}
        results: list[AuditExecutionResult] = []
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
            results.append(result)
        return tuple(results)

    return run_audits


def _cleanup_relations(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relations: tuple[str, ...],
    keep: bool,
    statement_recorder: StatementRecorder,
) -> None:
    """Drop cleanup relations on success, keep on failure."""

    if keep or not relations:
        return

    relation: str
    for relation in relations:
        try:
            adapter.drop(
                connection=connection,
                destination=relation,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        except Exception:
            pass
