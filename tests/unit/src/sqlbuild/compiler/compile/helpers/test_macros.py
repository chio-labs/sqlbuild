from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.helpers.render.macros import expand_sql_macros
from sqlbuild.compiler.compile.models.core import (
    LoadedMacro,
    MacroContext,
)
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    ExpandSqlMacrosErrorTestCase,
    ExpandSqlMacrosTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile.helpers.helpers import build_loaded_macros

_MACRO_CONTEXT: MacroContext = MacroContext(
    adapter_name="bigquery",
    sql_analysis_enabled=True,
    target_name="dev",
    vars={"project_name": "demo"},
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExpandSqlMacrosTestCase(
            description="uses macro override text instead of loaded macro function",
            macro_file_contents="""
def country() -> str:
    return "'CA'"
""".strip()
            + "\n",
            sql="SELECT @country() AS country",
            macro_overrides={"country": "'US'"},
            expected_sql="SELECT 'US' AS country",
        ),
        ExpandSqlMacrosTestCase(
            description="uses macro override text without evaluating macro arguments",
            macro_file_contents="""
def status(value: str) -> str:
    return value
""".strip()
            + "\n",
            sql="SELECT @status(@missing_nested()) AS status",
            macro_overrides={"status": "'paid'"},
            expected_sql="SELECT 'paid' AS status",
        ),
        ExpandSqlMacrosTestCase(
            description="expands nested macro arguments",
            macro_file_contents="""
def project_column() -> str:
    return "order_id"

def select_column(column_name: str) -> str:
    return f"SELECT {column_name}"
""".strip()
            + "\n",
            sql="@select_column(@project_column())",
            expected_sql="SELECT order_id",
        ),
        ExpandSqlMacrosTestCase(
            description="expands multiple nested macro arguments in one call",
            macro_file_contents="""
def left_column() -> str:
    return "order_id"

def right_column() -> str:
    return "customer_id"

def select_columns(left: str, right: str) -> str:
    return f"SELECT {left}, {right}"
""".strip()
            + "\n",
            sql="@select_columns(@left_column(), @right_column())",
            expected_sql="SELECT order_id, customer_id",
        ),
        ExpandSqlMacrosTestCase(
            description="expands ten nested macro calls in a chain",
            macro_file_contents="""
def step_1(value: str) -> str:
    return f"{value}_1"

def step_2(value: str) -> str:
    return f"{value}_2"

def step_3(value: str) -> str:
    return f"{value}_3"

def step_4(value: str) -> str:
    return f"{value}_4"

def step_5(value: str) -> str:
    return f"{value}_5"

def step_6(value: str) -> str:
    return f"{value}_6"

def step_7(value: str) -> str:
    return f"{value}_7"

def step_8(value: str) -> str:
    return f"{value}_8"

def step_9(value: str) -> str:
    return f"{value}_9"

def step_10(value: str) -> str:
    return f"SELECT {value}_10"
""".strip()
            + "\n",
            sql='@step_10(@step_9(@step_8(@step_7(@step_6(@step_5(@step_4(@step_3(@step_2(@step_1("base"))))))))))',
            expected_sql="SELECT base_1_2_3_4_5_6_7_8_9_10",
        ),
        ExpandSqlMacrosTestCase(
            description="ignores fake macro text inside line comments and strings",
            macro_file_contents="""
def project_columns() -> str:
    return "order_id, customer_id"
""".strip()
            + "\n",
            sql="""
-- @fake_macro()
SELECT '@fake_macro()' AS label, @project_columns() FROM raw_orders
""".strip(),
            expected_sql="""
-- @fake_macro()
SELECT '@fake_macro()' AS label, order_id, customer_id FROM raw_orders
""".strip(),
        ),
        ExpandSqlMacrosTestCase(
            description="ignores full email addresses and bare domains in comments and strings",
            macro_file_contents="""
def project_columns() -> str:
    return "order_id"
""".strip()
            + "\n",
            sql="""
-- contact: analyst@example.com and @example.com
SELECT
  'analyst@example.com' AS email_value,
  '@example.com' AS domain_value,
  @project_columns()
FROM raw_orders
""".strip(),
            expected_sql="""
-- contact: analyst@example.com and @example.com
SELECT
  'analyst@example.com' AS email_value,
  '@example.com' AS domain_value,
  order_id
FROM raw_orders
""".strip(),
        ),
        ExpandSqlMacrosTestCase(
            description="ignores fake macro text inside block comments and quoted identifiers",
            macro_file_contents="""
def project_columns() -> str:
    return "order_id"
""".strip()
            + "\n",
            sql="""
/* @fake_macro() */
SELECT `@fake_macro()` AS quoted_name, @project_columns() FROM raw_orders
""".strip(),
            expected_sql="""
/* @fake_macro() */
SELECT `@fake_macro()` AS quoted_name, order_id FROM raw_orders
""".strip(),
        ),
        ExpandSqlMacrosTestCase(
            description="passes compile macro context to ctx-aware macros",
            macro_file_contents="""
def adapter_name(ctx) -> str:
    return ctx.adapter_name
""".strip()
            + "\n",
            sql="SELECT @adapter_name() AS adapter_name",
            expected_sql="SELECT bigquery AS adapter_name",
        ),
        ExpandSqlMacrosTestCase(
            description="passes full compile macro context fields to ctx-aware macros",
            macro_file_contents="""
def context_summary(ctx) -> str:
    summary = (
        f"{ctx.adapter_name}|{ctx.sql_analysis_enabled}|"
        f"{ctx.target_name}|{ctx.vars['project_name']}"
    )
    return f"SELECT '{summary}'"
""".strip()
            + "\n",
            sql="@context_summary()",
            expected_sql="SELECT 'bigquery|True|dev|demo'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_macro_variants_when_expanding_then_it_returns_expected_sql(
    test_case: ExpandSqlMacrosTestCase,
    tmp_path: Path,
) -> None:
    loaded_macros: dict[str, LoadedMacro] = build_loaded_macros(
        tmp_path, test_case.macro_file_contents
    )

    expanded_sql: str = expand_sql_macros(
        sql=test_case.sql,
        file_path=tmp_path / "models" / "orders.sql",
        loaded_macros=loaded_macros,
        macro_overrides=test_case.macro_overrides,
        macro_context=_MACRO_CONTEXT,
    )

    assert expanded_sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ExpandSqlMacrosErrorTestCase(
            description="raises when a ctx-aware macro is called with reserved ctx kwarg",
            macro_file_contents="""
def adapter_name(ctx) -> str:
    return ctx.adapter_name
""".strip()
            + "\n",
            sql="SELECT @adapter_name(ctx='manual') FROM raw_orders",
            expected_error_fragment="reserved for injected macro context",
        ),
        ExpandSqlMacrosErrorTestCase(
            description="raises when a top level macro returns a non string",
            macro_file_contents="""
def bad_macro() -> list[str]:
    return ["order_id"]
""".strip()
            + "\n",
            sql="SELECT @bad_macro() FROM raw_orders",
            expected_error_fragment="must return a SQL string when used directly in SQL",
        ),
        ExpandSqlMacrosErrorTestCase(
            description="raises when macro output contains an unexpanded macro call",
            macro_file_contents="""
def outer_macro() -> str:
    return "@inner_macro()"

def inner_macro() -> str:
    return "order_id"
""".strip()
            + "\n",
            sql="SELECT @outer_macro() FROM raw_orders",
            expected_error_fragment=(
                r"produced output containing unexpanded macro call '@inner_macro\('"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_macro_usage_when_expanding_then_it_raises_clear_errors(
    test_case: ExpandSqlMacrosErrorTestCase,
    tmp_path: Path,
) -> None:
    loaded_macros: dict[str, LoadedMacro] = build_loaded_macros(
        tmp_path, test_case.macro_file_contents
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        expand_sql_macros(
            sql=test_case.sql,
            file_path=tmp_path / "models" / "orders.sql",
            loaded_macros=loaded_macros,
            macro_context=_MACRO_CONTEXT,
        )
