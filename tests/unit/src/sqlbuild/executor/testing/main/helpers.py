from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, SqlTestAssertionStep, SqlTestPlanEntry


def build_comparison_test_entry(*, sql_analysis_enabled: bool = True) -> SqlTestPlanEntry:
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
        sql_analysis_enabled=sql_analysis_enabled,
    )


def build_comparison_test_entry_with_helper_ctes(
    *, sql_analysis_enabled: bool = True
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
        sql_analysis_enabled=sql_analysis_enabled,
    )


def build_table_function_test_entry(
    *,
    sql_analysis_enabled: bool = True,
    resolved_sql: str = "SELECT * FROM `workspace`.`test`.`customer_orders`(1)",
) -> SqlTestPlanEntry:
    return SqlTestPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="customer_orders_table_fn",
        ),
        name="customer_orders_table_fn",
        chain=(
            ChainStep(
                model_name="table_fn returns customer orders",
                resolved_sql=resolved_sql,
                expected_cte_sql="SELECT 1 AS order_id",
            ),
        ),
        sql_analysis_enabled=sql_analysis_enabled,
    )


def build_assertion_test_entry(*, sql_analysis_enabled: bool = True) -> SqlTestPlanEntry:
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
        sql_analysis_enabled=sql_analysis_enabled,
    )


def build_comparison_test_adapter(
    adapter_name: str,
) -> DuckDbAdapter | SnowflakeAdapter | BigQueryAdapter | DatabricksAdapter:
    return {
        "bigquery": BigQueryAdapter,
        "databricks": DatabricksAdapter,
        "snowflake": SnowflakeAdapter,
        "duckdb": DuckDbAdapter,
    }[adapter_name]()
