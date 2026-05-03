"""View materialization lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.auditing.main import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.helpers.naming import build_qualified_name
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.spec.models.source import SourceEntry


def execute_view_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    run_id: str,
    fingerprint_schema: str | None,
) -> ModelExecutionResult:
    """Execute one view model through its full materialization lifecycle."""

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
        statement_recorder.record_many(render_hooks(hooks=entry.pre_hook, phase_label="pre_hook"))
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

    try:
        adapter.create_view_as(
            connection,
            target=target_qualified,
            sql=entry.resolved_sql,
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
        )

    audit_error: bool = False
    audit: AuditPlanEntry
    for audit in model_audits:
        result: AuditExecutionResult = execute_audit(
            audit=audit,
            adapter=adapter,
            connection=connection,
            model_targets=model_targets,
            seed_targets=seed_targets,
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
            error="view audit failed with error severity; view was already created",
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try:
        statement_recorder.record_many(render_hooks(hooks=entry.post_hook, phase_label="post_hook"))
        execute_hooks(
            connection=connection,
            adapter=adapter,
            hooks=entry.post_hook,
            phase_label="post_hook",
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
        )

    try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        fingerprint_schema=fingerprint_schema,
        warnings=warnings,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        executed_statements=statement_recorder.snapshot(),
    )
