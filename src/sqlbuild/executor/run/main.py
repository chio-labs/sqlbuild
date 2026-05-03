"""Single-model table execution lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.auditing.main import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks
from sqlbuild.executor.run.helpers.incremental import (
    execute_incremental_entry as execute_incremental_entry,
)
from sqlbuild.executor.run.helpers.microbatch import (
    execute_microbatch_entry as execute_microbatch_entry,
)
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.helpers.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.helpers.naming import build_qualified_name
from sqlbuild.executor.shared.types import (
    ExecutionPhase,
    ExecutionStatus,
    TablePromotionMode,
)
from sqlbuild.spec.models.source import SourceEntry


def execute_table_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    promotion_mode: TablePromotionMode,
    run_id: str,
    fingerprint_schema: str | None,
) -> ModelExecutionResult:
    """Execute one table model through its full materialization lifecycle."""

    target_database: str | None = entry.target.database
    target_schema: str | None = entry.target.schema
    target_table: str = entry.target.name
    target_qualified: str = build_qualified_name(
        database=target_database, schema=target_schema, name=target_table
    )
    staging_table: str = f"{target_table}__staging"
    staging_qualified: str = build_qualified_name(
        database=target_database, schema=target_schema, name=staging_table
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []

    try:
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
            model_targets=model_targets,
            seed_targets=seed_targets,
            source_map=source_map,
            model_audits=model_audits,
            declared_columns=declared_columns,
            run_id=run_id,
            fingerprint_schema=fingerprint_schema,
            warnings=warnings,
            audit_results=audit_results,
        )

    return _direct_lifecycle(
        entry=entry,
        adapter=adapter,
        connection=connection,
        target_qualified=target_qualified,
        model_targets=model_targets,
        seed_targets=seed_targets,
        source_map=source_map,
        model_audits=model_audits,
        declared_columns=declared_columns,
        run_id=run_id,
        fingerprint_schema=fingerprint_schema,
        warnings=warnings,
        audit_results=audit_results,
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
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    run_id: str,
    fingerprint_schema: str | None,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
) -> ModelExecutionResult:
    """Staged table lifecycle: CTAS staging, type enforce, audit, promote."""

    try:
        adapter.drop(connection, target=staging_qualified, if_exists=True)
        adapter.create_table_as(connection, target=staging_qualified, sql=entry.resolved_sql)
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
        )

    if entry.type_enforcement and declared_columns:
        try:
            enforce_types_staged(
                adapter=adapter,
                connection=connection,
                staging_qualified=staging_qualified,
                staging_database=target_database,
                staging_schema=target_schema,
                staging_table=staging_table,
                declared_columns=declared_columns,
            )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.TYPE_ENFORCEMENT,
                error=str(exc),
                staging_relation=staging_qualified,
                warnings=warnings,
                audit_results=audit_results,
            )

    overrides: dict[str, str] = {entry.name: staging_qualified}
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
            error="pre-promotion audit failed with error severity",
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
        )

    try:
        existing: bool = adapter.relation_exists(
            connection,
            database=target_database,
            schema=target_schema,
            name=target_table,
        )
        if existing:
            adapter.swap(connection, left=target_qualified, right=staging_qualified)
            adapter.drop(connection, target=staging_qualified, if_exists=True)
        else:
            adapter.rename(connection, source=staging_qualified, target=target_qualified)
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PROMOTION,
            error=str(exc),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
        )

    try:
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
    )


def _direct_lifecycle(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    target_qualified: str,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    run_id: str,
    fingerprint_schema: str | None,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
) -> ModelExecutionResult:
    """Direct table lifecycle: CTAS target, audit after, no staging."""

    if entry.type_enforcement and declared_columns:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.TYPE_ENFORCEMENT,
            error=(
                f"model '{entry.name}': type enforcement requires staged promotion mode "
                f"for runtime column inspection; set table_promotion_mode: staged in "
                f"sqlbuild_project.yml settings"
            ),
            warnings=warnings,
            audit_results=audit_results,
        )

    try:
        adapter.create_table_as(connection, target=target_qualified, sql=entry.resolved_sql)
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
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
            error="post-promotion audit failed with error severity; target was already updated",
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
        )

    try:
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
    )
