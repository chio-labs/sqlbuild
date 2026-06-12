from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo, SchemaDiffResult, StatementRecorder
from sqlbuild.adapters.postgres.client import PostgresAdapter
from sqlbuild.compiler.compile.models.core import FunctionArgument
from tests.unit.src.sqlbuild.adapters.postgres._test_types import (
    PostgresAdapterDefaultsTestCase,
    PostgresDescribeRelationTestCase,
    PostgresIndexSqlTestCase,
    PostgresLatestReadSqlTestCase,
    PostgresLoadSeedTestCase,
    PostgresMoveOrCopyRelationTestCase,
    PostgresPruneSqlTestCase,
    PostgresRenderCreateFunctionTestCase,
    PostgresRenderCreateTableAsTestCase,
    PostgresRenderIdentifierTestCase,
    PostgresRenderRenameTestCase,
    PostgresRenderSwapTestCase,
    PostgresSchemaDiffTestCase,
)
from tests.unit.src.sqlbuild.adapters.postgres.helpers import (
    FakePostgresConnection,
    FakePostgresCursor,
)

RENDER_CREATE_TABLE_AS_TEST_CASES: list[PostgresRenderCreateTableAsTestCase] = [
    PostgresRenderCreateTableAsTestCase(
        description="renders DROP then CREATE because Postgres has no CREATE OR REPLACE TABLE",
        target="public.fact_orders",
        sql="SELECT * FROM staging.fact_orders",
        expected_statements=(
            "DROP TABLE IF EXISTS public.fact_orders",
            "CREATE TABLE public.fact_orders AS SELECT * FROM staging.fact_orders",
        ),
    ),
    PostgresRenderCreateTableAsTestCase(
        description="renders DROP then CREATE for unqualified target",
        target="fact_orders",
        sql="SELECT id FROM src",
        expected_statements=(
            "DROP TABLE IF EXISTS fact_orders",
            "CREATE TABLE fact_orders AS SELECT id FROM src",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RENDER_CREATE_TABLE_AS_TEST_CASES,
    ids=[case.description for case in RENDER_CREATE_TABLE_AS_TEST_CASES],
)
def test_given_table_target_when_rendering_create_then_postgres_drops_before_create(
    test_case: PostgresRenderCreateTableAsTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    statements: tuple[str, ...] = adapter.render_create_table_as(
        destination=test_case.target,
        sql=test_case.sql,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresRenderCreateFunctionTestCase(
            description="renders SQL function with explicit language",
            expected_statements=(
                "CREATE OR REPLACE FUNCTION public.is_completed_order(order_status TEXT)\n"
                "RETURNS BOOLEAN\n"
                "LANGUAGE SQL AS $$\n"
                "SELECT order_status = 'completed'\n"
                "$$",
            ),
        )
    ],
    ids=["renders SQL function with explicit language"],
)
def test_given_sql_function_when_rendering_create_then_postgres_declares_language(
    test_case: PostgresRenderCreateFunctionTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        destination="public.is_completed_order",
        arguments=(FunctionArgument(name="order_status", type="TEXT"),),
        returns="BOOLEAN",
        body_sql="SELECT order_status = 'completed'",
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresIndexSqlTestCase(
            description="renders latest-read index for fingerprint table",
            database=None,
            schema="analytics",
            expected_statements=(
                "CREATE INDEX IF NOT EXISTS analytics._sqlbuild_fingerprints_latest_idx "
                "ON analytics._sqlbuild_fingerprints (node_type, node_name, ts DESC, run_id DESC)",
            ),
        )
    ],
    ids=["renders latest-read index for fingerprint table"],
)
def test_given_fingerprint_table_when_rendering_indexes_then_postgres_uses_latest_read_keys(
    test_case: PostgresIndexSqlTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    statements: tuple[str, ...] = adapter.render_create_fingerprint_index_sqls(
        database=test_case.database,
        schema=test_case.schema,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresIndexSqlTestCase(
            description="renders latest-read index for source freshness table",
            database=None,
            schema="analytics",
            expected_statements=(
                "CREATE INDEX IF NOT EXISTS analytics._sqlbuild_source_freshness_latest_idx "
                "ON analytics._sqlbuild_source_freshness ("
                "source_name, target_database, target_schema, target_name, "
                "observed_at DESC, run_id DESC)",
            ),
        )
    ],
    ids=["renders latest-read index for source freshness table"],
)
def test_given_source_freshness_table_when_rendering_indexes_then_postgres_uses_latest_read_keys(
    test_case: PostgresIndexSqlTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    statements: tuple[str, ...] = adapter.render_create_source_freshness_index_sqls(
        database=test_case.database,
        schema=test_case.schema,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresLatestReadSqlTestCase(
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
    ids=["renders windowed fingerprint latest read"],
)
def test_given_fingerprint_table_when_rendering_latest_read_then_postgres_uses_window_query(
    test_case: PostgresLatestReadSqlTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

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
        PostgresLatestReadSqlTestCase(
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
    ids=["renders windowed source freshness latest read"],
)
def test_given_source_freshness_when_rendering_latest_read_then_postgres_uses_window_query(
    test_case: PostgresLatestReadSqlTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

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
        PostgresPruneSqlTestCase(
            description="renders fingerprint pruning with ctid window delete",
            database=None,
            schema="analytics",
            retain_versions=5,
            expected_fragments=(
                "DELETE FROM analytics._sqlbuild_fingerprints WHERE ctid IN",
                "ROW_NUMBER() OVER",
                "PARTITION BY node_type, node_name",
                "ORDER BY ts DESC, run_id DESC",
                "__sqlbuild_history_rank > 5",
            ),
        )
    ],
    ids=["renders fingerprint pruning with ctid window delete"],
)
def test_given_fingerprint_table_when_rendering_prune_then_postgres_uses_history_rank(
    test_case: PostgresPruneSqlTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

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
        PostgresPruneSqlTestCase(
            description="renders source freshness pruning with full identity",
            database=None,
            schema="analytics",
            retain_versions=3,
            expected_fragments=(
                "DELETE FROM analytics._sqlbuild_source_freshness WHERE ctid IN",
                "ROW_NUMBER() OVER",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                "__sqlbuild_history_rank > 3",
            ),
        )
    ],
    ids=["renders source freshness pruning with full identity"],
)
def test_given_source_freshness_table_when_rendering_prune_then_postgres_uses_history_rank(
    test_case: PostgresPruneSqlTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    sql: str = adapter.render_prune_source_freshness_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


RENDER_RENAME_TEST_CASES: list[PostgresRenderRenameTestCase] = [
    PostgresRenderRenameTestCase(
        description="strips schema prefix from target — Postgres RENAME TO is unqualified",
        source="public.orders__staging",
        target="public.orders",
        expected_statement="ALTER TABLE public.orders__staging RENAME TO orders",
    ),
    PostgresRenderRenameTestCase(
        description="strips three-part prefix leaving bare table name",
        source="mydb.public.orders",
        target="mydb.public.orders_new",
        expected_statement="ALTER TABLE mydb.public.orders RENAME TO orders_new",
    ),
    PostgresRenderRenameTestCase(
        description="passes through unqualified source and target unchanged",
        source="orders",
        target="orders_new",
        expected_statement="ALTER TABLE orders RENAME TO orders_new",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RENDER_RENAME_TEST_CASES,
    ids=[case.description for case in RENDER_RENAME_TEST_CASES],
)
def test_given_qualified_names_when_renaming_then_postgres_uses_unqualified_target(
    test_case: PostgresRenderRenameTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    (statement,) = adapter.render_rename(origin=test_case.source, destination=test_case.target)

    assert statement == test_case.expected_statement


POSTGRES_MOVE_OR_COPY_RELATION_TEST_CASES: list[PostgresMoveOrCopyRelationTestCase] = [
    PostgresMoveOrCopyRelationTestCase(
        description="moves table across schemas with rename before set schema",
        source="public.fact_orders",
        target="public__sqb_physical.fact_orders__v_abc123",
        expected_statements=(
            "ALTER TABLE public.fact_orders RENAME TO fact_orders__v_abc123",
            "ALTER TABLE public.fact_orders__v_abc123 SET SCHEMA public__sqb_physical",
        ),
    ),
    PostgresMoveOrCopyRelationTestCase(
        description="moves table across schemas without renaming when names match",
        source="public.fact_orders",
        target="public__sqb_physical.fact_orders",
        expected_statements=("ALTER TABLE public.fact_orders SET SCHEMA public__sqb_physical",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    POSTGRES_MOVE_OR_COPY_RELATION_TEST_CASES,
    ids=[case.description for case in POSTGRES_MOVE_OR_COPY_RELATION_TEST_CASES],
)
def test_given_cross_schema_table_move_when_moving_then_postgres_uses_native_move(
    test_case: PostgresMoveOrCopyRelationTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    cursor: FakePostgresCursor = FakePostgresCursor()
    connection: FakePostgresConnection = FakePostgresConnection(cursor)
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


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresRenderSwapTestCase(
            description="renders three-rename swap with unqualified intermediate target names",
            left="public.orders",
            right="public.orders__staging",
            expected_statements=(
                "ALTER TABLE public.orders RENAME TO orders__swap_staging",
                "ALTER TABLE public.orders__staging RENAME TO orders",
                "ALTER TABLE public.orders__swap_staging RENAME TO orders__staging",
            ),
        )
    ],
    ids=["renders three-rename swap with unqualified intermediate target names"],
)
def test_given_two_relations_when_swapping_then_postgres_uses_three_rename_approach(
    test_case: PostgresRenderSwapTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    statements: tuple[str, ...] = adapter.render_swap(left=test_case.left, right=test_case.right)

    assert statements == test_case.expected_statements


DESCRIBE_RELATION_TEST_CASES: list[PostgresDescribeRelationTestCase] = [
    PostgresDescribeRelationTestCase(
        description="returns columns from information_schema for a schema-qualified relation",
        relation="public.fact_orders",
        cursor_rows=(("id", "integer"), ("total", "numeric"), ("created_at", "timestamp")),
        expected_columns=(
            ColumnInfo(name="id", type="integer"),
            ColumnInfo(name="total", type="numeric"),
            ColumnInfo(name="created_at", type="timestamp"),
        ),
    ),
    PostgresDescribeRelationTestCase(
        description="returns columns for an unqualified relation name",
        relation="fact_orders",
        cursor_rows=(("id", "integer"),),
        expected_columns=(ColumnInfo(name="id", type="integer"),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DESCRIBE_RELATION_TEST_CASES,
    ids=[case.description for case in DESCRIBE_RELATION_TEST_CASES],
)
def test_given_relation_when_describing_then_postgres_queries_information_schema(
    test_case: PostgresDescribeRelationTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    cursor: FakePostgresCursor = FakePostgresCursor(rows=test_case.cursor_rows)
    connection: FakePostgresConnection = FakePostgresConnection(cursor)

    columns: tuple[ColumnInfo, ...] = adapter.describe_relation(connection, test_case.relation)

    assert columns == test_case.expected_columns
    assert len(connection.executed_sql) == 1
    assert "information_schema.columns" in connection.executed_sql[0]


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresAdapterDefaultsTestCase(
            description="returns expected Postgres adapter defaults and dialect settings",
            expected_default_schema="public",
            expected_default_database=None,
            expected_sql_analysis_dialect="postgres",
            expected_identifier_length=63,
        )
    ],
    ids=["returns expected Postgres adapter defaults and dialect settings"],
)
def test_given_postgres_adapter_when_checking_defaults_then_returns_expected_values(
    test_case: PostgresAdapterDefaultsTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    assert adapter.default_schema() == test_case.expected_default_schema
    assert adapter.default_database() == test_case.expected_default_database
    assert adapter.sql_analysis_dialect() == test_case.expected_sql_analysis_dialect
    assert adapter.maximum_identifier_length() == test_case.expected_identifier_length


LOAD_SEED_TEST_CASES: list[PostgresLoadSeedTestCase] = [
    PostgresLoadSeedTestCase(
        description="loads CSV rows via executemany with correct column order",
        csv_text='id,name\n1,"Liege waffle"\n2,Stroopwafel\n',
        expected_rows=[("1", "Liege waffle"), ("2", "Stroopwafel")],
    ),
    PostgresLoadSeedTestCase(
        description="handles empty CSV by skipping executemany",
        csv_text="id,name\n",
        expected_rows=[],
    ),
]

POSTGRES_RENDER_IDENTIFIER_TEST_CASES: list[PostgresRenderIdentifierTestCase] = [
    PostgresRenderIdentifierTestCase(
        description="quotes lowercase identifiers without changing case",
        name="event_id",
        expected_identifier='"event_id"',
    ),
    PostgresRenderIdentifierTestCase(
        description="escapes embedded double quotes",
        name='event"id',
        expected_identifier='"event""id"',
    ),
]


@pytest.mark.parametrize(
    "test_case",
    POSTGRES_RENDER_IDENTIFIER_TEST_CASES,
    ids=[case.description for case in POSTGRES_RENDER_IDENTIFIER_TEST_CASES],
)
def test_given_identifier_when_rendering_then_postgres_quotes_identifier(
    test_case: PostgresRenderIdentifierTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()

    identifier: str = adapter.render_identifier(test_case.name)

    assert identifier == test_case.expected_identifier


@pytest.mark.parametrize(
    "test_case",
    LOAD_SEED_TEST_CASES,
    ids=[case.description for case in LOAD_SEED_TEST_CASES],
)
def test_given_seed_csv_when_loading_then_postgres_uses_executemany(
    test_case: PostgresLoadSeedTestCase,
    tmp_path: Path,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    cursor: FakePostgresCursor = FakePostgresCursor()
    connection: FakePostgresConnection = FakePostgresConnection(cursor)
    seed_file: Path = tmp_path / "seed.csv"
    seed_file.write_text(test_case.csv_text, encoding="utf-8")

    adapter.load_seed(
        connection,
        destination="public.waffle_types",
        file_path=seed_file,
        columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        replace=False,
        statement_recorder=StatementRecorder(),
    )

    assert cursor.executemany_rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresSchemaDiffTestCase(
            description="treats semantically equivalent numeric types as unchanged",
            expected_result=SchemaDiffResult(),
        )
    ],
    ids=["treats semantically equivalent numeric types as unchanged"],
)
def test_given_equivalent_types_when_diffing_schema_then_postgres_ignores_alias_only_changes(
    test_case: PostgresSchemaDiffTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    # information_schema returns lowercase type names; NUMERIC(10,2) and numeric(10,2)
    # must be treated as identical after the type normalizer applies case folding.
    monkeypatch.setattr(
        adapter,
        "describe_relation",
        lambda connection, relation: (
            (ColumnInfo(name="total", type="NUMERIC(10,2)"),)
            if relation == "left_relation"
            else (ColumnInfo(name="total", type="numeric(10,2)"),)
        ),
    )

    result: SchemaDiffResult = adapter.diff_schema(
        connection=object(),
        left="left_relation",
        right="right_relation",
    )

    assert result == test_case.expected_result
