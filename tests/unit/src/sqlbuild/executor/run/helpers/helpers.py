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


class FakeCursorAdapter:
    def execute(self, connection: Any, sql: str) -> Any:
        return connection.execute(sql)


def build_name_test_adapter(adapter_name: str) -> DuckDbAdapter | BigQueryAdapter:
    if adapter_name == "bigquery":
        return BigQueryAdapter()
    return DuckDbAdapter()
