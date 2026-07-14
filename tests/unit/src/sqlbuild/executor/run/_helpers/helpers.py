from pathlib import Path
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.models import ColumnInfo
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.models import HookContext


def insert_snapshot_hook_log(ctx: HookContext, phase: str) -> None:
    ctx.execute_sql(f"INSERT INTO {ctx.destination.schema}.snapshot_hook_log VALUES ('{phase}')")


def fail_snapshot_hook(ctx: HookContext, message: str) -> None:
    raise RuntimeError(message)


def build_result_model_plan_entry() -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name="orders",
        ),
        name="orders",
        relative_path=Path("models/orders.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None,
            schema="analytics",
            name="orders",
            qualified_name="analytics.orders",
        ),
        fingerprint_query_sql="SELECT 1 AS id",
        resolved_sql="SELECT 1 AS id",
        logical_ddl="CREATE TABLE analytics.orders AS SELECT 1 AS id",
    )


def build_contract_model_plan_entry(
    *, contract_enforced: bool, contract_columns: tuple[ColumnInfo, ...]
) -> ModelPlanEntry:
    entry: ModelPlanEntry = build_result_model_plan_entry()
    return ModelPlanEntry(
        key=entry.key,
        name=entry.name,
        relative_path=entry.relative_path,
        materialization_type=entry.materialization_type,
        action=entry.action,
        reason=entry.reason,
        destination=entry.destination,
        fingerprint_query_sql=entry.fingerprint_query_sql,
        resolved_sql=entry.resolved_sql,
        logical_ddl=entry.logical_ddl,
        contract_enforced=contract_enforced,
        contract_columns=contract_columns,
    )


def build_snapshot_execution_plan_entry(
    *,
    pre_hooks: object = None,
    post_hooks: object = None,
    contract_enforced: bool = False,
    contract_columns: tuple[ColumnInfo, ...] = (),
) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name="customer_snapshot",
        ),
        name="customer_snapshot",
        relative_path=Path("models/customer_snapshot.sql"),
        materialization_type=MaterializationType.SNAPSHOT,
        action=PlanAction.SNAPSHOT,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name="customer_snapshot",
            qualified_name="main.customer_snapshot",
        ),
        fingerprint_query_sql="SELECT 1 AS customer_id",
        resolved_sql=(
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at"
        ),
        logical_ddl="",
        unique_key=("customer_id",),
        snapshot_strategy="timestamp",
        updated_at_column="updated_at",
        contract_enforced=contract_enforced,
        contract_columns=contract_columns,
        pre_hooks=pre_hooks,
        post_hooks=post_hooks,
    )


class FakeCursorAdapter:
    def __init__(self, *, target_relation_exists: bool = False) -> None:
        self.target_relation_exists: bool = target_relation_exists

    def execute(self, connection: Any, sql: str) -> Any:
        return connection.execute(sql)

    def relation_exists(
        self, connection: Any, *, database: str | None, schema: str | None, name: str
    ) -> bool:
        del connection, database, schema, name
        return self.target_relation_exists

    def requires_derived_table_aliases(self) -> bool:
        return False


def build_name_test_adapter(adapter_name: str) -> DuckDbAdapter | BigQueryAdapter:
    if adapter_name == "bigquery":
        return BigQueryAdapter()
    return DuckDbAdapter()


def build_fingerprint_audit_plan_entry() -> AuditPlanEntry:
    return build_fingerprint_audit_plan_entry_with_options()


def build_fingerprint_audit_plan_entry_with_options(
    *,
    name: str = "not_null_orders",
    severity: str = AuditSeverity.ERROR.value,
    attached_column_name: str | None = "order_id",
    resolved_sql: str = "SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
    always_run: bool = False,
) -> AuditPlanEntry:
    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=resolved_sql,
        unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity(severity),
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        attached_target_name="orders",
        attached_column_name=attached_column_name,
        always_run=always_run,
    )


def build_fingerprint_audit_result(
    *,
    outcome: str,
    audit_name: str = "not_null_orders",
    severity: str = AuditSeverity.ERROR.value,
    attached_column_name: str | None = "order_id",
) -> AuditExecutionResult:
    return AuditExecutionResult(
        audit_name=audit_name,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity(severity),
        outcome=AuditOutcome(outcome),
        row_count=0 if outcome == AuditOutcome.PASS.value else 1,
        executed_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
        run_scope_phase=AuditRunScope.FINAL,
        attached_target_name="orders",
        attached_column_name=attached_column_name,
    )


class FakeRelationReuseAdapter(BaseAdapter):
    adapter_name: str = "fake_relation_reuse"

    def __init__(self, *, supports_zero_copy_clone: bool) -> None:
        self._supports_zero_copy_clone: bool = supports_zero_copy_clone
        self.calls: list[str] = []
        self.sql: str | None = None

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def execute(self, connection: Any, sql: str) -> object:
        del connection, sql
        return object()

    def close(self, connection: Any) -> None:
        del connection

    def supports_zero_copy_clone(self) -> bool:
        self.calls.append("supports_zero_copy_clone")
        return self._supports_zero_copy_clone

    def clone(
        self,
        connection: Any,
        *,
        origin: str,
        destination: str,
        hard_copy: bool = False,
        origin_is_transient: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, origin, destination, hard_copy, origin_is_transient, statement_recorder
        self.calls.append("clone")

    def durable_clone(
        self,
        connection: Any,
        *,
        origin: str,
        destination: str,
        origin_is_transient: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, origin, destination, origin_is_transient, statement_recorder
        self.calls.append("durable_clone")

    def create_table_as(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        config: dict[str, Any] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, destination, config, statement_recorder
        self.calls.append("create_table_as")
        self.sql = sql
