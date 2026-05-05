from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo, SchemaDiffResult
from sqlbuild.adapter.shared.types import CursorKind
from sqlbuild.compiler.compile.models import FunctionArgument
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.integrations.snowflake.client import SnowflakeAdapter
from tests.unit.src.sqlbuild.integrations.snowflake._test_types import (
    SnowflakeRenderCursorBoundLiteralTestCase,
    SnowflakeRenderPythonFunctionTestCase,
    SnowflakeSchemaDiffTestCase,
)

TEST_CASES: list[SnowflakeRenderCursorBoundLiteralTestCase] = [
    SnowflakeRenderCursorBoundLiteralTestCase(
        description="renders timestamp cursor bounds as typed literals",
        value="2024-01-15T00:00:00",
        cursor_type=CursorKind.TIMESTAMP,
        expected_literal="TIMESTAMP '2024-01-15T00:00:00'",
    ),
    SnowflakeRenderCursorBoundLiteralTestCase(
        description="renders integer cursor bounds without quotes",
        value="42",
        cursor_type=CursorKind.INTEGER,
        expected_literal="42",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_cursor_bounds_when_rendering_then_snowflake_returns_expected_literal(
    test_case: SnowflakeRenderCursorBoundLiteralTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    result: str = adapter.render_cursor_bound_literal(test_case.value, test_case.cursor_type)

    assert result == test_case.expected_literal


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderPythonFunctionTestCase(
            description="renders Python UDF DDL with runtime handler and packages",
            expected_sql=(
                "CREATE OR REPLACE FUNCTION "
                "udf_db.udf_schema.is_positive_int(a_string STRING)\n"
                "RETURNS INTEGER\n"
                "LANGUAGE PYTHON\n"
                "RUNTIME_VERSION = '3.11'\n"
                "HANDLER = 'main'\n"
                "PACKAGES = ('numpy','pandas==1.5.0')\n"
                "AS $$\n"
                "def main(a_string):\n"
                "    return 1 if a_string else 0\n"
                "$$"
            ),
        )
    ],
    ids=["renders Python UDF DDL with runtime handler and packages"],
)
def test_given_python_function_when_rendering_then_snowflake_returns_expected_ddl(
    test_case: SnowflakeRenderPythonFunctionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        target="udf_db.udf_schema.is_positive_int",
        arguments=(FunctionArgument(name="a_string", type="STRING"),),
        returns="INTEGER",
        body_sql="def main(a_string):\n    return 1 if a_string else 0",
        language=FunctionLanguage.PYTHON,
        runtime_version="3.11",
        entry_point="main",
        packages=("numpy", "pandas==1.5.0"),
    )

    assert statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeSchemaDiffTestCase(
            description="treats semantically equivalent numeric types as unchanged",
            expected_result=SchemaDiffResult(),
        )
    ],
    ids=["treats semantically equivalent numeric types as unchanged"],
)
def test_given_equivalent_types_when_diffing_schema_then_snowflake_ignores_alias_only_changes(
    test_case: SnowflakeSchemaDiffTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    monkeypatch.setattr(
        adapter,
        "describe_relation",
        lambda connection, relation: (
            (ColumnInfo(name="id", type="NUMBER(38,0)"),)
            if relation == "left_relation"
            else (ColumnInfo(name="id", type="DECIMAL(38,0)"),)
        ),
    )

    result: SchemaDiffResult = adapter.diff_schema(
        connection=object(),
        left="left_relation",
        right="right_relation",
    )

    assert result == test_case.expected_result
