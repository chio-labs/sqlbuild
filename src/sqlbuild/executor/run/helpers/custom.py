"""Custom materialization execution lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo, StatementRecorder
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry, SchemaFinding
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.executor.auditing.main import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.helpers.naming import build_qualified_name
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context
from sqlbuild.spec.models.source import SourceEntry


def execute_custom_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    materialize_fn: Callable[[MaterializationContext], MaterializationResult],
    run_id: str,
    fingerprint_schema: str | None,
    environment: str,
    effective_vars: dict[str, str],
    existing_relation: RelationInfo | None,
    on_progress: Callable[[str], None] | None = None,
) -> ModelExecutionResult:
    """Execute one model through the custom materialization lifecycle."""

    target_database: str | None = entry.target.database
    target_schema: str | None = entry.target.schema
    target_name: str = entry.target.name
    target_qualified: str = build_qualified_name(
        database=target_database, schema=target_schema, name=target_name
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()

    try:
        with diagnostics_context(sqlbuild_phase="pre_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.pre_hook,
                phase_label="pre_hook",
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PRE_HOOK,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    config_dict: dict[str, Any] = dict(entry.custom_config)
    placeholders_dict: dict[str, str] = dict(entry.custom_placeholders)

    run_audits_fn: Callable[[str], tuple[AuditExecutionResult, ...]] = _build_run_audits(
        model_audits=model_audits,
        adapter=adapter,
        connection=connection,
        model_targets=model_targets,
        seed_targets=seed_targets,
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
        target=target_qualified,
        target_database=target_database,
        target_schema=target_schema,
        target_name=target_name,
        sql=entry.resolved_sql,
        config=config_dict,
        placeholders=placeholders_dict,
        existing_relation=existing_relation,
        run_id=run_id,
        environment=environment,
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
    )

    try:
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="custom"):
            result: MaterializationResult = materialize_fn(ctx)
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    if result.failed:
        user_audit_results: list[AuditExecutionResult] = (
            list(result.audit_results) if result.audit_results is not None else []
        )
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
            error=result.error or "custom materialization reported failure",
            warnings=warnings,
            audit_results=user_audit_results,
            statement_recorder=statement_recorder,
        )

    if result.audit_results is not None:
        audit_results.extend(result.audit_results)
    else:
        audit_error: bool = False
        audit: AuditPlanEntry
        for audit in model_audits:
            audit_result: AuditExecutionResult = execute_audit(
                audit=audit,
                adapter=adapter,
                connection=connection,
                model_targets=model_targets,
                seed_targets=seed_targets,
                source_map=source_map,
                relation_overrides=None,
                run_scope_phase=AuditRunScope.FINAL,
            )
            audit_results.append(audit_result)
            if audit_result.outcome == AuditOutcome.ERROR:
                audit_error = True

        if audit_error:
            _cleanup_relations(
                adapter=adapter,
                connection=connection,
                relations=result.cleanup_relations,
                keep=True,
                statement_recorder=statement_recorder,
            )
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.AUDIT,
                error="post-materialization audit failed with error severity",
                promoted_relation=result.relation,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

    try:
        with diagnostics_context(sqlbuild_phase="post_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hook,
                phase_label="post_hook",
            )
    except Exception as exc:
        _cleanup_relations(
            adapter=adapter,
            connection=connection,
            relations=result.cleanup_relations,
            keep=True,
            statement_recorder=statement_recorder,
        )
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.POST_HOOK,
            error=str(exc),
            promoted_relation=result.relation,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        fingerprint_schema=fingerprint_schema,
        warnings=warnings,
    )

    _cleanup_relations(
        adapter=adapter,
        connection=connection,
        relations=result.cleanup_relations,
        keep=False,
        statement_recorder=statement_recorder,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=result.relation,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
    )


def _build_run_audits(
    *,
    model_audits: tuple[AuditPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
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
                model_targets=model_targets,
                seed_targets=seed_targets,
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
                connection,
                target=relation,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        except Exception:
            pass
