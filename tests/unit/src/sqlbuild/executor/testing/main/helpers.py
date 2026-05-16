from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, SqlTestAssertionStep, SqlTestPlanEntry
from sqlbuild.integrations.bigquery.client import BigQueryAdapter
from sqlbuild.integrations.databricks.client import DatabricksAdapter
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


def build_comparison_test_entry_with_helper_ctes(
    *, sqlglot_enabled: bool = True
) -> SqlTestPlanEntry:
    helper_with_sql: str = "WITH input_values AS (SELECT 1 AS order_id)"
    expected_helper_with_sql: str = "WITH INPUT_VALUES AS (SELECT 1 AS order_id)"
    return SqlTestPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="orders_chain",
        ),
        name="orders_chain",
        chain=(
            ChainStep(
                model_name="orders",
                resolved_sql=f"{helper_with_sql} SELECT order_id FROM input_values",
                expected_cte_sql=f"{expected_helper_with_sql} SELECT order_id FROM INPUT_VALUES",
            ),
        ),
        sqlglot_enabled=sqlglot_enabled,
    )


def build_table_function_test_entry(*, sqlglot_enabled: bool = True) -> SqlTestPlanEntry:
    return SqlTestPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="customer_orders_table_fn",
        ),
        name="customer_orders_table_fn",
        chain=(
            ChainStep(
                model_name="table_fn returns customer orders",
                resolved_sql=("SELECT * FROM `workspace`.`test`.`customer_orders`(1)"),
                expected_cte_sql="SELECT 1 AS order_id",
            ),
        ),
        sqlglot_enabled=sqlglot_enabled,
    )


def build_assertion_test_entry(*, sqlglot_enabled: bool = True) -> SqlTestPlanEntry:
    return SqlTestPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="orders_assertions",
        ),
        name="orders_assertions",
        chain=(
            ChainStep(
                model_name="orders",
                resolved_sql="SELECT 1 AS order_id, 10 AS amount",
            ),
        ),
        assertions=(
            SqlTestAssertionStep(
                name="no_negative_orders",
                resolved_sql="SELECT * FROM __actual__orders WHERE amount < 0",
            ),
        ),
        sqlglot_enabled=sqlglot_enabled,
    )


def build_comparison_test_adapter(
    adapter_name: str,
) -> DuckDbAdapter | SnowflakeAdapter | BigQueryAdapter | DatabricksAdapter:
    if adapter_name == "bigquery":
        return BigQueryAdapter()
    if adapter_name == "databricks":
        return DatabricksAdapter()
    if adapter_name == "snowflake":
        return SnowflakeAdapter()
    return DuckDbAdapter()
