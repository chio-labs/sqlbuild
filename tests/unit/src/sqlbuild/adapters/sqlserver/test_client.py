from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapters.sqlserver.client import SqlServerAdapter
from sqlbuild.compiler.compile.models.core import FunctionArgument
from tests.unit.src.sqlbuild.adapters.sqlserver._test_types import (
    SqlServerAdapterDefaultsTestCase,
    SqlServerMoveOrCopyRelationTestCase,
    SqlServerRenderCreateFunctionTestCase,
    SqlServerRenderCreateSchemaTestCase,
    SqlServerRenderCreateTableAsTestCase,
    SqlServerRenderIdentifierTestCase,
)
from tests.unit.src.sqlbuild.adapters.sqlserver.helpers import FakeSqlServerConnection


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerAdapterDefaultsTestCase(
            description="returns expected SQL Server adapter defaults and dialect settings",
            expected_default_schema="dbo",
            expected_default_database=None,
            expected_sql_analysis_dialect="tsql",
            expected_identifier_length=128,
        )
    ],
    ids=["returns expected SQL Server adapter defaults and dialect settings"],
)
def test_given_sqlserver_adapter_when_checking_defaults_then_returns_expected_values(
    test_case: SqlServerAdapterDefaultsTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    assert adapter.default_schema() == test_case.expected_default_schema
    assert adapter.default_database() == test_case.expected_default_database
    assert adapter.sql_analysis_dialect() == test_case.expected_sql_analysis_dialect
    assert adapter.maximum_identifier_length() == test_case.expected_identifier_length


SQLSERVER_RENDER_IDENTIFIER_TEST_CASES: list[SqlServerRenderIdentifierTestCase] = [
    SqlServerRenderIdentifierTestCase(
        description="quotes identifiers with brackets",
        name="event_id",
        expected_identifier="[event_id]",
    ),
    SqlServerRenderIdentifierTestCase(
        description="escapes embedded closing bracket",
        name="event]id",
        expected_identifier="[event]]id]",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SQLSERVER_RENDER_IDENTIFIER_TEST_CASES,
    ids=[case.description for case in SQLSERVER_RENDER_IDENTIFIER_TEST_CASES],
)
def test_given_identifier_when_rendering_then_sqlserver_bracket_quotes_identifier(
    test_case: SqlServerRenderIdentifierTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    identifier: str = adapter.render_identifier(test_case.name)

    assert identifier == test_case.expected_identifier


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerRenderCreateTableAsTestCase(
            description="renders drop and select into for table replacement",
            target="dbo.fact_orders",
            sql="SELECT id FROM dbo.stg_orders",
            expected_statements=(
                "DROP TABLE IF EXISTS dbo.fact_orders",
                "SELECT * INTO dbo.fact_orders FROM "
                "(SELECT id FROM dbo.stg_orders) AS __create_source",
            ),
        )
    ],
    ids=["renders drop and select into for table replacement"],
)
def test_given_table_target_when_rendering_create_then_sqlserver_uses_select_into(
    test_case: SqlServerRenderCreateTableAsTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_create_table_as(
        target=test_case.target,
        sql=test_case.sql,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerRenderCreateFunctionTestCase(
            description="renders scalar SQL function with T-SQL body",
            expected_statements=(
                "CREATE OR ALTER FUNCTION dbo.is_completed_order(@order_status NVARCHAR(MAX))\n"
                "RETURNS BIT\n"
                "AS\n"
                "BEGIN\n"
                "    RETURN (CASE WHEN @order_status = 'completed' THEN 1 ELSE 0 END)\n"
                "END",
            ),
        )
    ],
    ids=["renders scalar SQL function with T-SQL body"],
)
def test_given_sql_function_when_rendering_create_then_sqlserver_declares_function_body(
    test_case: SqlServerRenderCreateFunctionTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        target="dbo.is_completed_order",
        arguments=(FunctionArgument(name="order_status", type="NVARCHAR(MAX)"),),
        returns="BIT",
        body_sql="SELECT order_status = 'completed'",
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerRenderCreateSchemaTestCase(
            description="renders conditional schema creation",
            schema="analytics",
            expected_statement=(
                "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'analytics') "
                "EXEC('CREATE SCHEMA [analytics]')"
            ),
        )
    ],
    ids=["renders conditional schema creation"],
)
def test_given_schema_when_rendering_create_then_sqlserver_checks_sys_schemas(
    test_case: SqlServerRenderCreateSchemaTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    (statement,) = adapter.render_create_schema(database=None, schema=test_case.schema)

    assert statement == test_case.expected_statement


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerMoveOrCopyRelationTestCase(
            description="moves table across schemas with transfer and rename",
            source="[marts].[fact_orders]",
            target="[marts__sqb_physical].[fact_orders__v_abc123]",
            expected_statements=(
                "ALTER SCHEMA [marts__sqb_physical] TRANSFER [marts].[fact_orders]",
                "EXEC sp_rename '[marts__sqb_physical].[fact_orders]', 'fact_orders__v_abc123'",
            ),
        )
    ],
    ids=["moves table across schemas with transfer and rename"],
)
def test_given_cross_schema_table_move_when_moving_then_sqlserver_uses_native_transfer(
    test_case: SqlServerMoveOrCopyRelationTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: FakeSqlServerConnection = FakeSqlServerConnection()
    statement_recorder: StatementRecorder = StatementRecorder()

    adapter.move_or_copy_relation(
        connection,
        origin=test_case.source,
        destination=test_case.target,
        remove_origin=True,
        allow_copy_fallback=False,
        statement_recorder=statement_recorder,
    )

    assert tuple(connection.executed_sql) == test_case.expected_statements
    assert tuple(event.content for event in statement_recorder.snapshot()) == (
        test_case.expected_statements
    )
