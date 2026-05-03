"""Test helpers for custom materialization integration tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult
from sqlbuild.executor.run.helpers.custom import execute_custom_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.integrations.duckdb.client import DuckDbAdapter


def build_custom_plan_entry(
    *,
    name: str = "test_model",
    sql: str = "SELECT 1 AS id",
    reason: PlanReason = PlanReason.NO_CHANGE,
    pre_hook: object = None,
    post_hook: object = None,
    custom_config: dict[str, object] | None = None,
    custom_placeholders: dict[str, str] | None = None,
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for a custom materialization."""

    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.CUSTOM,
        action=PlanAction.CUSTOM,
        reason=reason,
        target=CompiledRelationTarget(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        resolved_sql=sql,
        logical_ddl="",
        custom_materialization_name="test_custom",
        custom_config=custom_config if custom_config is not None else {"test_key": "test_value"},
        custom_placeholders=custom_placeholders if custom_placeholders is not None else {},
        pre_hook=pre_hook,
        post_hook=post_hook,
    )


def build_passing_audit(*, name: str, target_name: str) -> AuditPlanEntry:
    """Build an audit that returns 0 rows (PASS)."""

    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=f'SELECT * FROM __ref("{target_name}") WHERE 1=0',
        unresolved_sql=f'SELECT * FROM __ref("{target_name}") WHERE 1=0',
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.ERROR,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        attached_target_name=target_name,
    )


def build_failing_audit(*, name: str, target_name: str) -> AuditPlanEntry:
    """Build an audit that returns rows (ERROR)."""

    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=f'SELECT * FROM __ref("{target_name}")',
        unresolved_sql=f'SELECT * FROM __ref("{target_name}")',
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.ERROR,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        attached_target_name=target_name,
    )


def run_custom_entry(
    *,
    adapter: DuckDbAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    materialize_fn: Callable[[MaterializationContext], MaterializationResult],
    model_audits: tuple[AuditPlanEntry, ...] = (),
    model_targets: dict[str, CompiledRelationTarget] | None = None,
    existing_relation: RelationInfo | None = None,
    environment: str = "test",
    effective_vars: dict[str, str] | None = None,
) -> ModelExecutionResult:
    """Execute a custom materialization lifecycle with full control over parameters."""

    return execute_custom_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_targets=model_targets or {},
        seed_targets={},
        source_map={},
        model_audits=model_audits,
        declared_columns=(),
        materialize_fn=materialize_fn,
        run_id="test_run",
        fingerprint_schema=None,
        environment=environment,
        effective_vars=effective_vars or {},
        existing_relation=existing_relation,
    )


def relation_exists(connection: Any, *, schema: str, name: str) -> bool:
    """Check if a relation exists in the warehouse."""

    cursor: Any = connection.execute(
        f"SELECT 1 FROM information_schema.tables "
        f"WHERE table_schema = '{schema}' AND table_name = '{name}'"
    )
    return cursor.fetchone() is not None


def row_count(connection: Any, *, qualified_name: str) -> int:
    """Count rows in a relation."""

    cursor: Any = connection.execute(f"SELECT COUNT(*) FROM {qualified_name}")
    return cursor.fetchone()[0]


_FN_REGISTRY: dict[
    str, Callable[[], Callable[[MaterializationContext], MaterializationResult]]
] = {}


def resolve_fn(name: str) -> Callable[[MaterializationContext], MaterializationResult]:
    """Resolve a materialize function builder by name and call it."""

    return _FN_REGISTRY[name]()


def build_simple_fn() -> Callable[[MaterializationContext], MaterializationResult]:
    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        ctx.adapter.create_table_as(ctx.connection, target=ctx.target, sql=ctx.sql)
        return MaterializationResult(relation=ctx.target)

    return materialize


def build_failing_fn() -> Callable[[MaterializationContext], MaterializationResult]:
    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        return MaterializationResult(
            relation=ctx.target, failed=True, error="user-reported failure"
        )

    return materialize


def build_excepting_fn() -> Callable[[MaterializationContext], MaterializationResult]:
    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        raise RuntimeError("materialization crashed")

    return materialize


def build_staging_fn() -> Callable[[MaterializationContext], MaterializationResult]:
    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        staging: str = f"{ctx.target}__staging"
        ctx.adapter.create_table_as(ctx.connection, target=staging, sql=ctx.sql)
        ctx.adapter.rename(ctx.connection, source=staging, target=ctx.target)
        return MaterializationResult(relation=ctx.target, cleanup_relations=(staging,))

    return materialize


def build_audit_running_fn() -> Callable[[MaterializationContext], MaterializationResult]:
    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        staging: str = f"{ctx.target}__staging"
        ctx.adapter.create_table_as(ctx.connection, target=staging, sql=ctx.sql)
        audit_results: tuple[AuditExecutionResult, ...] = ctx.run_audits(staging)
        ctx.adapter.rename(ctx.connection, source=staging, target=ctx.target)
        return MaterializationResult(
            relation=ctx.target, cleanup_relations=(staging,), audit_results=audit_results
        )

    return materialize


def build_user_audit_fn(
    *, expect_pass: bool
) -> Callable[[MaterializationContext], MaterializationResult]:
    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        staging: str = f"{ctx.target}__staging"
        ctx.adapter.create_table_as(ctx.connection, target=staging, sql=ctx.sql)
        audit_results: tuple[AuditExecutionResult, ...] = ctx.run_audits(staging)
        has_error: bool = any(r.outcome == AuditOutcome.ERROR for r in audit_results)
        if has_error:
            return MaterializationResult(
                relation=ctx.target,
                failed=True,
                error="audit failed",
                cleanup_relations=(staging,),
                audit_results=audit_results,
            )
        ctx.adapter.rename(ctx.connection, source=staging, target=ctx.target)
        return MaterializationResult(
            relation=ctx.target, cleanup_relations=(staging,), audit_results=audit_results
        )

    return materialize


def build_cleanup_fn(*, fail: bool) -> Callable[[MaterializationContext], MaterializationResult]:
    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        staging: str = f"{ctx.target}__staging"
        ctx.adapter.create_table_as(ctx.connection, target=ctx.target, sql=ctx.sql)
        ctx.adapter.create_table_as(
            ctx.connection, target=staging, sql="SELECT 1 AS cleanup_marker"
        )
        if fail:
            return MaterializationResult(
                relation=ctx.target,
                failed=True,
                error="intentional failure",
                cleanup_relations=(staging,),
            )
        return MaterializationResult(relation=ctx.target, cleanup_relations=(staging,))

    return materialize


_FN_REGISTRY["simple"] = build_simple_fn
_FN_REGISTRY["failing"] = build_failing_fn
_FN_REGISTRY["excepting"] = build_excepting_fn
_FN_REGISTRY["staging"] = build_staging_fn
_FN_REGISTRY["audit_running"] = build_audit_running_fn
