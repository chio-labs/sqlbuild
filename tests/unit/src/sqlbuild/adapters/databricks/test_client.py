from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.adapter.shared.types import FunctionNullabilityRule
from sqlbuild.adapters.databricks.client import DatabricksAdapter
from sqlbuild.compiler.compile.models.core import (
    FunctionArgument,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.lineage.types import InferredNullability
from tests.unit.src.sqlbuild.adapters.databricks._test_types import (
    DatabricksExpressionInferenceProfileTestCase,
    DatabricksPythonFunctionSupportTestCase,
    DatabricksRenderCloneTestCase,
    DatabricksRenderDeleteInsertCursorTestCase,
    DatabricksRenderDurableCloneTestCase,
    DatabricksRenderPythonFunctionTestCase,
    DatabricksRenderTableFunctionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksExpressionInferenceProfileTestCase(
            description="returns Databricks inference rules",
            expected_sql_analysis_dialect="databricks",
            expected_identifier_limit=255,
            expected_rule_results={
                "IF": InferredNullability.NON_NULL,
                "LOWER": InferredNullability.NON_NULL,
            },
        )
    ],
    ids=["returns Databricks inference rules"],
)
def test_given_databricks_adapter_when_getting_inference_profile_then_returns_expected_rules(
    test_case: DatabricksExpressionInferenceProfileTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()

    assert profile.sql_analysis_dialect == test_case.expected_sql_analysis_dialect
    assert adapter.maximum_identifier_length() == test_case.expected_identifier_limit
    if_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("IF")
    lower_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("LOWER")
    assert if_rule is not None
    assert lower_rule is not None
    assert (
        if_rule(
            (
                InferredNullability.UNKNOWN,
                InferredNullability.NON_NULL,
                InferredNullability.NON_NULL,
            )
        )
        == test_case.expected_rule_results["IF"]
    )
    assert lower_rule((InferredNullability.NON_NULL,)) == test_case.expected_rule_results["LOWER"]


TEST_CASES: list[DatabricksRenderDeleteInsertCursorTestCase] = [
    DatabricksRenderDeleteInsertCursorTestCase(
        description="renders replace where for timestamp cursor bounds",
        target="`workspace`.`test`.`orders`",
        sql="SELECT * FROM `workspace`.`test`.`orders__delta`",
        cursor_column="ordered_at",
        cursor_start="2026-01-01 00:00:00",
        cursor_end="2026-01-02 00:00:00",
        columns=None,
        expected_statements=(
            "INSERT INTO `workspace`.`test`.`orders` REPLACE WHERE "
            "`ordered_at` >= TIMESTAMP '2026-01-01 00:00:00' AND "
            "`ordered_at` < TIMESTAMP '2026-01-02 00:00:00' "
            "SELECT * FROM `workspace`.`test`.`orders__delta`",
        ),
    ),
    DatabricksRenderDeleteInsertCursorTestCase(
        description="renders replace where with explicit columns",
        target="`workspace`.`test`.`orders`",
        sql="SELECT id, status FROM `workspace`.`test`.`orders__delta`",
        cursor_column="id",
        cursor_start="1",
        cursor_end="10",
        columns=("id", "status"),
        expected_statements=(
            "INSERT INTO `workspace`.`test`.`orders` (`id`, `status`) REPLACE WHERE "
            "`id` >= 1 AND `id` < 10 "
            "SELECT id, status FROM `workspace`.`test`.`orders__delta`",
        ),
    ),
]

DATABRICKS_RENDER_CLONE_TEST_CASES: list[DatabricksRenderCloneTestCase] = [
    DatabricksRenderCloneTestCase(
        description="renders shallow table clone by default",
        source="`workspace`.`prod`.`fact_orders`",
        target="`workspace`.`dev`.`fact_orders`",
        hard_copy=False,
        expected_statements=(
            "CREATE TABLE `workspace`.`dev`.`fact_orders` "
            "SHALLOW CLONE `workspace`.`prod`.`fact_orders`",
        ),
        expected_supports_zero_copy=True,
    ),
    DatabricksRenderCloneTestCase(
        description="renders CTAS when hard copy is requested",
        source="`workspace`.`prod`.`fact_orders`",
        target="`workspace`.`dev`.`fact_orders`",
        hard_copy=True,
        expected_statements=(
            "CREATE OR REPLACE TABLE `workspace`.`dev`.`fact_orders` AS "
            "SELECT * FROM `workspace`.`prod`.`fact_orders`",
        ),
        expected_supports_zero_copy=True,
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_cursor_delete_insert_when_rendering_then_databricks_uses_replace_where(
    test_case: DatabricksRenderDeleteInsertCursorTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    statements: tuple[str, ...] = adapter.render_delete_insert_cursor(
        target=test_case.target,
        sql=test_case.sql,
        cursor_column=test_case.cursor_column,
        cursor_start=test_case.cursor_start,
        cursor_end=test_case.cursor_end,
        columns=test_case.columns,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    DATABRICKS_RENDER_CLONE_TEST_CASES,
    ids=[case.description for case in DATABRICKS_RENDER_CLONE_TEST_CASES],
)
def test_given_clone_request_when_rendering_then_databricks_uses_expected_clone_sql(
    test_case: DatabricksRenderCloneTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    statements: tuple[str, ...] = adapter.render_clone(
        origin=test_case.source,
        destination=test_case.target,
        hard_copy=test_case.hard_copy,
    )

    assert adapter.supports_zero_copy_clone() is test_case.expected_supports_zero_copy
    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksRenderDurableCloneTestCase(
            description="renders deep clone for durable physical versions",
            source="`workspace`.`prod`.`fact_orders`",
            target="`workspace`.`dev`.`fact_orders`",
            expected_statements=(
                "CREATE TABLE `workspace`.`dev`.`fact_orders` "
                "DEEP CLONE `workspace`.`prod`.`fact_orders`",
            ),
            expected_supports_durable_clone=True,
        )
    ],
    ids=["renders deep clone for durable physical versions"],
)
def test_given_durable_clone_request_when_rendering_then_databricks_uses_deep_clone_sql(
    test_case: DatabricksRenderDurableCloneTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    statements: tuple[str, ...] = adapter.render_durable_clone(
        origin=test_case.source,
        destination=test_case.target,
    )

    assert adapter.supports_durable_clone() is test_case.expected_supports_durable_clone
    assert statements == test_case.expected_statements


DATABRICKS_RENDER_PYTHON_FUNCTION_TEST_CASES: list[DatabricksRenderPythonFunctionTestCase] = [
    DatabricksRenderPythonFunctionTestCase(
        description="renders Python UDF DDL with unwrapped function body",
        body_sql=(
            "def main(order_status: str | None) -> bool:\n    return order_status == 'completed'"
        ),
        packages=(),
        expected_statements=(
            "CREATE OR REPLACE FUNCTION `workspace`.`test`.`is_completed_order_py`"
            "(order_status STRING)\n"
            "RETURNS BOOLEAN\n"
            "LANGUAGE PYTHON\n"
            "AS $$\n"
            "return order_status == 'completed'\n"
            "$$",
        ),
    ),
    DatabricksRenderPythonFunctionTestCase(
        description="renders Python UDF DDL with imports helpers and dependencies",
        body_sql=(
            "import json\n\n"
            "def normalize(value):\n"
            "    return value.strip()\n\n"
            "def main(order_status: str | None) -> bool:\n"
            "    if order_status is None:\n"
            "        return False\n"
            "    return normalize(order_status) == 'completed'"
        ),
        packages=("simplejson==3.19.3",),
        expected_statements=(
            "CREATE OR REPLACE FUNCTION `workspace`.`test`.`is_completed_order_py`"
            "(order_status STRING)\n"
            "RETURNS BOOLEAN\n"
            "LANGUAGE PYTHON\n"
            "ENVIRONMENT (\n"
            "  dependencies = '[\"simplejson==3.19.3\"]',\n"
            "  environment_version = 'None'\n"
            ")\n"
            "AS $$\n"
            "import json\n\n"
            "def normalize(value):\n"
            "    return value.strip()\n"
            "if order_status is None:\n"
            "    return False\n"
            "return normalize(order_status) == 'completed'\n"
            "$$",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DATABRICKS_RENDER_PYTHON_FUNCTION_TEST_CASES,
    ids=[case.description for case in DATABRICKS_RENDER_PYTHON_FUNCTION_TEST_CASES],
)
def test_given_python_function_when_rendering_then_databricks_returns_expected_ddl(
    test_case: DatabricksRenderPythonFunctionTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        target="`workspace`.`test`.`is_completed_order_py`",
        arguments=(FunctionArgument(name="order_status", type="STRING"),),
        returns="BOOLEAN",
        body_sql=test_case.body_sql,
        language=FunctionLanguage.PYTHON,
        runtime_version="3.11",
        entry_point="main",
        packages=test_case.packages,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksPythonFunctionSupportTestCase(
            description="supports Python function execution",
            expected_supports_python_functions=True,
        )
    ],
    ids=["supports Python function execution"],
)
def test_given_databricks_adapter_when_checking_capabilities_then_python_functions_supported(
    test_case: DatabricksPythonFunctionSupportTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    assert adapter.supports_python_functions() is test_case.expected_supports_python_functions


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksRenderTableFunctionTestCase(
            description="renders SQL table function DDL",
            expected_statements=(
                "CREATE OR REPLACE FUNCTION `workspace`.`test`.`customer_orders`"
                "(p_customer_id INT)\n"
                "RETURNS TABLE\n"
                "RETURN SELECT order_id FROM `workspace`.`test`.`fact_orders`\n"
                "WHERE customer_id = p_customer_id",
            ),
        )
    ],
    ids=["renders SQL table function DDL"],
)
def test_given_table_function_when_rendering_then_databricks_returns_expected_ddl(
    test_case: DatabricksRenderTableFunctionTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        target="`workspace`.`test`.`customer_orders`",
        arguments=(FunctionArgument(name="p_customer_id", type="INT"),),
        returns="TABLE",
        body_sql=(
            "SELECT order_id FROM `workspace`.`test`.`fact_orders`\n"
            "WHERE customer_id = p_customer_id"
        ),
        return_columns=(FunctionReturnColumn(name="order_id", type="INT"),),
    )

    assert statements == test_case.expected_statements
