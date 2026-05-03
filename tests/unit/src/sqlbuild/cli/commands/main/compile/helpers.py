from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    ChainStep,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus


def build_target_writer_plan_output() -> PlanOutput:
    """Build a plan output covering every target writer artifact type."""

    model_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    seed_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SEED,
        name="country_codes",
    )
    audit_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.AUDIT,
        name="not_null",
    )
    test_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SQL_TEST,
        name="orders_chain",
    )
    target: CompiledRelationTarget = CompiledRelationTarget(
        database=None,
        schema="analytics",
        name="orders",
        qualified_name="analytics.orders",
    )
    return PlanOutput(
        model_entries=(
            ModelPlanEntry(
                key=model_key,
                name="orders",
                relative_path=Path("staging/orders.sql"),
                materialization_type=MaterializationType.TABLE,
                action=PlanAction.CREATE_TABLE,
                reason=PlanReason.FIRST_RUN,
                target=target,
                resolved_sql="SELECT 1 AS order_id",
                logical_ddl="CREATE TABLE analytics.orders AS SELECT 1 AS order_id",
            ),
        ),
        seed_entries=(
            SeedPlanEntry(
                key=seed_key,
                name="country_codes",
                target=target,
                file_path=Path("seeds/country_codes.csv"),
                columns=(),
            ),
        ),
        audit_entries=(
            AuditPlanEntry(
                key=audit_key,
                name="not_null",
                resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
                unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
                attachment_kind=AuditAttachmentKind.MODEL,
                severity=AuditSeverity.WARN,
                requested_run_scope=AuditRunScope.FINAL,
                effective_run_scope=AuditRunScope.FINAL,
                attached_target_name="orders",
                attached_column_name="order_id",
            ),
        ),
        test_entries=(
            SqlTestPlanEntry(
                key=test_key,
                name="orders_chain",
                chain=(
                    ChainStep(
                        model_name="stg_orders",
                        resolved_sql="SELECT 1 AS order_id",
                        expected_cte_sql="SELECT 1 AS order_id",
                    ),
                    ChainStep(
                        model_name="orders",
                        resolved_sql="SELECT order_id FROM stg_orders",
                        expected_cte_sql="SELECT 1 AS order_id",
                    ),
                ),
            ),
        ),
    )


def read_target_files(target_dir: Path, expected_files: dict[str, str]) -> dict[str, str]:
    """Read expected target files into a comparable mapping."""

    return {
        relative_path: (target_dir / relative_path).read_text(encoding="utf-8")
        for relative_path in expected_files
    }


def build_runtime_target_execution_result() -> BuildExecutionResult:
    return BuildExecutionResult(
        status=BuildStatus.SUCCESS,
        model_results=(
            ModelExecutionResult(
                model_name="orders",
                status=ExecutionStatus.SUCCESS,
                lifecycle_events=(
                    LifeCycleEvent(
                        kind=LifeCycleEventKind.SQL,
                        content="DROP TABLE IF EXISTS analytics.orders__staging",
                    ),
                    LifeCycleEvent(
                        kind=LifeCycleEventKind.SQL,
                        content="CREATE OR REPLACE TABLE analytics.orders__staging "
                        "AS SELECT 1 AS order_id",
                    ),
                ),
            ),
        ),
        success_count=1,
    )
