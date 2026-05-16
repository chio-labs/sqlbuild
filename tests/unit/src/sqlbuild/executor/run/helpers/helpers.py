from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationTarget,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.integrations.bigquery.client import BigQueryAdapter
from sqlbuild.integrations.duckdb.client import DuckDbAdapter


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
        target=CompiledRelationTarget(
            database=None,
            schema="analytics",
            name="orders",
            qualified_name="analytics.orders",
        ),
        fingerprint_query_sql="SELECT 1 AS id",
        resolved_sql="SELECT 1 AS id",
        logical_ddl="CREATE TABLE analytics.orders AS SELECT 1 AS id",
    )


def build_snapshot_execution_plan_entry(
    *,
    pre_hook: object = None,
    post_hook: object = None,
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
        target=CompiledRelationTarget(
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
        pre_hook=pre_hook,
        post_hook=post_hook,
    )


class FakeCursorAdapter:
    def execute(self, connection: Any, sql: str) -> Any:
        return connection.execute(sql)


def build_name_test_adapter(adapter_name: str) -> DuckDbAdapter | BigQueryAdapter:
    if adapter_name == "bigquery":
        return BigQueryAdapter()
    return DuckDbAdapter()
