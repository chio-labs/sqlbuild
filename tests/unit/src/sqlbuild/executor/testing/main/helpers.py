from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.integrations.bigquery.client import BigQueryAdapter
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from sqlbuild.integrations.snowflake.client import SnowflakeAdapter


def build_comparison_test_entry(*, sqlglot_enabled: bool = True) -> SqlTestPlanEntry:
    return SqlTestPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="orders_chain",
        ),
        name="orders_chain",
        chain=(
            ChainStep(
                model_name="orders",
                resolved_sql="SELECT 1 AS order_id",
                expected_cte_sql="SELECT 2 AS order_id",
            ),
        ),
        sqlglot_enabled=sqlglot_enabled,
    )


def build_comparison_test_adapter(
    adapter_name: str,
) -> DuckDbAdapter | SnowflakeAdapter | BigQueryAdapter:
    if adapter_name == "bigquery":
        return BigQueryAdapter()
    if adapter_name == "snowflake":
        return SnowflakeAdapter()
    return DuckDbAdapter()
