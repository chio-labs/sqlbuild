from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.adapters.bigquery.client import BigQueryAdapter
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationDestination,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason


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
        target=CompiledRelationDestination(
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
        target=entry.target,
        fingerprint_query_sql=entry.fingerprint_query_sql,
        resolved_sql=entry.resolved_sql,
        logical_ddl=entry.logical_ddl,
        contract_enforced=contract_enforced,
        contract_columns=contract_columns,
    )


def build_snapshot_execution_plan_entry(
    *,
    pre_hook: object = None,
    post_hook: object = None,
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
        target=CompiledRelationDestination(
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
        pre_hook=pre_hook,
        post_hook=post_hook,
    )


class FakeCursorAdapter:
    def execute(self, connection: Any, sql: str) -> Any:
        return connection.execute(sql)

    def requires_derived_table_aliases(self) -> bool:
        return False


def build_name_test_adapter(adapter_name: str) -> DuckDbAdapter | BigQueryAdapter:
    if adapter_name == "bigquery":
        return BigQueryAdapter()
    return DuckDbAdapter()
