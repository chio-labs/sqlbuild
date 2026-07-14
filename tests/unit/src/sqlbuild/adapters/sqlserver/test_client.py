from __future__ import annotations

import pytest

from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile.models import FunctionArgument
from tests.unit.src.sqlbuild.adapters.sqlserver._test_types import (
    SqlServerAdapterDefaultsTestCase,
    SqlServerIndexSqlTestCase,
    SqlServerLatestReadSqlTestCase,
    SqlServerMoveOrCopyRelationTestCase,
    SqlServerPruneSqlTestCase,
    SqlServerRenderCreateFunctionTestCase,
    SqlServerRenderCreateSchemaTestCase,
    SqlServerRenderCreateTableAsTestCase,
    SqlServerRenderIdentifierTestCase,
    SqlServerRenderQualifiedNameTestCase,
    SqlServerRenderRenameTestCase,
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
    ids=lambda case: case.description,
)
def test_given_sqlserver_adapter_when_checking_defaults_then_returns_expected_values(
    test_case: SqlServerAdapterDefaultsTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    assert adapter.default_schema() == test_case.expected_default_schema
    assert adapter.default_database() == test_case.expected_default_database
    assert adapter.sql_analysis_dialect() == test_case.expected_sql_analysis_dialect
    assert adapter.maximum_identifier_length() == test_case.expected_identifier_length


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
        SqlServerRenderQualifiedNameTestCase(
            description="renders three part qualified name",
            database="tempdb",
            schema="analytics_dev",
            name="fact_orders",
            expected_name="tempdb.analytics_dev.fact_orders",
        ),
        SqlServerRenderQualifiedNameTestCase(
            description="renders schema qualified name",
            database=None,
            schema="analytics_dev",
            name="fact_orders",
            expected_name="analytics_dev.fact_orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relation_parts_when_rendering_qualified_name_then_sqlserver_joins_parts(
    test_case: SqlServerRenderQualifiedNameTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    qualified_name: str | None = adapter.render_qualified_name(
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert qualified_name == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerRenderRenameTestCase(
            description="renders sp_rename without database and without quoted destination name",
            origin="[tempdb].[analytics_dev].[fact_orders__sqlbuild_reuse_stage]",
            destination='"tempdb"."analytics_dev"."fact_orders"',
            expected_statements=(
                "EXEC sp_rename '[analytics_dev].[fact_orders__sqlbuild_reuse_stage]', "
                "'fact_orders'",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_quoted_dbt_relation_when_rendering_rename_then_sqlserver_normalizes_names(
    test_case: SqlServerRenderRenameTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_rename(
        origin=test_case.origin,
        destination=test_case.destination,
    )

    assert statements == test_case.expected_statements


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
    ids=lambda case: case.description,
)
def test_given_table_target_when_rendering_create_then_sqlserver_uses_select_into(
    test_case: SqlServerRenderCreateTableAsTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_create_table_as(
        destination=test_case.target,
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
    ids=lambda case: case.description,
)
def test_given_sql_function_when_rendering_create_then_sqlserver_declares_function_body(
    test_case: SqlServerRenderCreateFunctionTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        destination="dbo.is_completed_order",
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
    ids=lambda case: case.description,
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
        SqlServerIndexSqlTestCase(
            description="renders guarded latest-read index for fingerprint table",
            database=None,
            schema="analytics",
            expected_statements=(
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
                "WHERE name = '_sqlbuild_fingerprints_latest_idx' "
                "AND object_id = OBJECT_ID(N'analytics._sqlbuild_fingerprints')) "
                "CREATE INDEX _sqlbuild_fingerprints_latest_idx "
                "ON analytics._sqlbuild_fingerprints (node_type, node_name, ts DESC, run_id DESC)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_table_when_rendering_indexes_then_sqlserver_uses_latest_read_keys(
    test_case: SqlServerIndexSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_create_fingerprint_index_sqls(
        database=test_case.database,
        schema=test_case.schema,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerIndexSqlTestCase(
            description="renders guarded latest-read index for source freshness table",
            database=None,
            schema="analytics",
            expected_statements=(
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
                "WHERE name = '_sqlbuild_source_freshness_latest_idx' "
                "AND object_id = OBJECT_ID(N'analytics._sqlbuild_source_freshness')) "
                "CREATE INDEX _sqlbuild_source_freshness_latest_idx "
                "ON analytics._sqlbuild_source_freshness ("
                "source_name, target_database, target_schema, target_name, "
                "observed_at DESC, run_id DESC)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_table_when_rendering_indexes_then_sqlserver_uses_latest_read_keys(
    test_case: SqlServerIndexSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_create_source_freshness_index_sqls(
        database=test_case.database,
        schema=test_case.schema,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerLatestReadSqlTestCase(
            description="renders guarded node result table create",
            database=None,
            schema="analytics",
            expected_fragments=(
                "IF NOT EXISTS (SELECT 1 FROM information_schema.tables ",
                "WHERE table_schema = 'analytics' AND table_name = '_sqlbuild_node_results')",
                "CREATE TABLE analytics._sqlbuild_node_results (",
                "node_type NVARCHAR(450) NOT NULL",
                "ts DATETIME2 NOT NULL",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_node_result_table_when_rendering_create_then_sqlserver_guards_missing_table(
    test_case: SqlServerLatestReadSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statement: str = adapter.render_create_node_result_table_sql(
        database=test_case.database,
        schema=test_case.schema,
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in statement


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerLatestReadSqlTestCase(
            description="renders bounded fingerprint key columns",
            database=None,
            schema="analytics",
            expected_fragments=(
                "IF NOT EXISTS (SELECT 1 FROM information_schema.tables ",
                "WHERE table_schema = 'analytics' AND table_name = '_sqlbuild_fingerprints')",
                "CREATE TABLE analytics._sqlbuild_fingerprints (",
                "node_type NVARCHAR(450) NOT NULL",
                "node_name NVARCHAR(450) NOT NULL",
                "run_id NVARCHAR(450) NOT NULL",
                "definition_hash NVARCHAR(450) NOT NULL",
                "definition_b64 NVARCHAR(MAX) NOT NULL",
                "metadata_json_b64 NVARCHAR(MAX) NOT NULL",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_table_when_rendering_create_then_sqlserver_uses_indexable_keys(
    test_case: SqlServerLatestReadSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statement: str = adapter.render_create_fingerprint_table_sql(
        database=test_case.database,
        schema=test_case.schema,
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in statement


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerIndexSqlTestCase(
            description="renders guarded lookup indexes for node result table",
            database=None,
            schema="analytics",
            expected_statements=(
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
                "WHERE name = '_sqlbuild_node_results_latest_idx' "
                "AND object_id = OBJECT_ID(N'analytics._sqlbuild_node_results')) "
                "CREATE INDEX _sqlbuild_node_results_latest_idx "
                "ON analytics._sqlbuild_node_results ("
                "node_type, node_name, target_database, target_schema, target_name, status, "
                "ts DESC, run_id DESC)",
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
                "WHERE name = '_sqlbuild_node_results_run_id_idx' "
                "AND object_id = OBJECT_ID(N'analytics._sqlbuild_node_results')) "
                "CREATE INDEX _sqlbuild_node_results_run_id_idx "
                "ON analytics._sqlbuild_node_results ("
                "run_id, node_type, node_name, target_database, target_schema, target_name)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_node_result_table_when_rendering_indexes_then_sqlserver_uses_lookup_keys(
    test_case: SqlServerIndexSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    statements: tuple[str, ...] = adapter.render_create_node_result_index_sqls(
        database=test_case.database,
        schema=test_case.schema,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerLatestReadSqlTestCase(
            description="renders windowed fingerprint latest read",
            database=None,
            schema="analytics",
            expected_fragments=(
                "ROW_NUMBER() OVER",
                "PARTITION BY node_type, node_name",
                "ORDER BY ts DESC, run_id DESC",
                "FROM analytics._sqlbuild_fingerprints",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_table_when_rendering_latest_read_then_sqlserver_uses_window_query(
    test_case: SqlServerLatestReadSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    sql: str = adapter.render_read_latest_fingerprints_sql(
        database=test_case.database,
        schema=test_case.schema,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerLatestReadSqlTestCase(
            description="renders windowed source freshness latest read",
            database=None,
            schema="analytics",
            expected_fragments=(
                "ROW_NUMBER() OVER",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                "FROM analytics._sqlbuild_source_freshness",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_when_rendering_latest_read_then_sqlserver_uses_window_query(
    test_case: SqlServerLatestReadSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    sql: str = adapter.render_read_latest_source_freshness_sql(
        database=test_case.database,
        schema=test_case.schema,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerPruneSqlTestCase(
            description="renders fingerprint pruning with writable ranked CTE",
            database=None,
            schema="analytics",
            retain_versions=5,
            expected_fragments=(
                "WITH __sqlbuild_ranked AS",
                "FROM analytics._sqlbuild_fingerprints",
                "PARTITION BY node_type, node_name",
                "ORDER BY ts DESC, run_id DESC",
                "DELETE FROM __sqlbuild_ranked WHERE __sqlbuild_history_rank > 5",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_table_when_rendering_prune_then_sqlserver_uses_history_rank(
    test_case: SqlServerPruneSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    sql: str = adapter.render_prune_fingerprint_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerPruneSqlTestCase(
            description="renders source freshness pruning with full identity",
            database=None,
            schema="analytics",
            retain_versions=3,
            expected_fragments=(
                "WITH __sqlbuild_ranked AS",
                "FROM analytics._sqlbuild_source_freshness",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                "DELETE FROM __sqlbuild_ranked WHERE __sqlbuild_history_rank > 3",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_table_when_rendering_prune_then_sqlserver_uses_history_rank(
    test_case: SqlServerPruneSqlTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()

    sql: str = adapter.render_prune_source_freshness_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


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
    ids=lambda case: case.description,
)
def test_given_cross_schema_table_move_when_moving_then_sqlserver_uses_native_transfer(
    test_case: SqlServerMoveOrCopyRelationTestCase,
) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: FakeSqlServerConnection = FakeSqlServerConnection()
    statement_recorder: StatementRecorder = StatementRecorder()

    adapter.move_or_copy_relation(
        connection=connection,
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
