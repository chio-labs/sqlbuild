from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    QueryResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    SchemaDiffResult,
    StatementRecorder,
)
from sqlbuild.integrations.postgres.client import PostgresAdapter
from tests.integration.src.sqlbuild.integrations.postgres._test_types import (
    PostgresBuildFlowTestCase,
    PostgresMergeTestCase,
    PostgresQueryTestCase,
    PostgresRowDiffSampleTestCase,
    PostgresRowDiffTestCase,
    PostgresSchemaDiffTestCase,
    PostgresSchemaIntrospectionTestCase,
    PostgresSeedTestCase,
)
from tests.integration.src.sqlbuild.integrations.postgres.helpers import (
    build_statement_recorder,
    fetch_rows,
    qualified_name,
    write_seed_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresSchemaIntrospectionTestCase(
            description="describes columns in ordinal position order",
            table_name="orders",
            ddl="CREATE TABLE {target} (id INTEGER, total NUMERIC(10,2), created_at TIMESTAMP)",
            expected_columns=(
                ColumnInfo(name="id", type="integer"),
                ColumnInfo(name="total", type="numeric"),
                ColumnInfo(name="created_at", type="timestamp without time zone"),
            ),
        )
    ],
    ids=["describes columns in ordinal position order"],
)
def test_given_table_when_describing_then_postgres_returns_columns_in_order(
    test_case: PostgresSchemaIntrospectionTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    target: str = qualified_name(schema=postgres_schema, name=test_case.table_name)
    adapter.execute(connection, test_case.ddl.format(target=target))

    columns: tuple[ColumnInfo, ...] = adapter.describe_relation(connection, target)

    assert columns == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresQueryTestCase(
            description="returns inline query result with column names and rows",
            sql="SELECT 1 AS id, 'hello' AS name",
            expected_result=QueryResult(
                columns=("id", "name"),
                rows=((1, "hello"),),
            ),
        )
    ],
    ids=["returns inline query result with column names and rows"],
)
def test_given_sql_when_querying_then_postgres_returns_named_rows(
    test_case: PostgresQueryTestCase,
    adapter: PostgresAdapter,
    connection: Any,
) -> None:
    result: QueryResult = adapter.query(connection, test_case.sql, limit=None)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresBuildFlowTestCase(
            description="creates table from query and promotes via atomic swap",
            table_name="fact_orders",
            source_sql="SELECT generate_series AS id FROM generate_series(1, 5)",
            expected_row_count=5,
        )
    ],
    ids=["creates table from query and promotes via atomic swap"],
)
def test_given_model_sql_when_building_then_postgres_creates_and_promotes_table(
    test_case: PostgresBuildFlowTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    recorder: StatementRecorder = build_statement_recorder()
    target: str = qualified_name(schema=postgres_schema, name=test_case.table_name)
    staging: str = qualified_name(schema=postgres_schema, name=f"{test_case.table_name}__staging")

    adapter.create_table_as(
        connection, target=staging, sql=test_case.source_sql, statement_recorder=recorder
    )
    adapter.create_table_as(
        connection, target=target, sql=f"SELECT * FROM {staging}", statement_recorder=recorder
    )
    adapter.swap(connection, left=target, right=staging, statement_recorder=recorder)

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=connection, sql=f"SELECT COUNT(*) FROM {target}"
    )
    assert rows[0][0] == test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresMergeTestCase(
            description="upserts rows on unique key conflict using ON CONFLICT DO UPDATE",
            table_name="customers",
            initial_sql="SELECT 1 AS id, 'Alice' AS name",
            merge_sql="SELECT 1 AS id, 'Alice Updated' AS name UNION ALL SELECT 2, 'Bob'",
            unique_key=("id",),
            expected_rows=((1, "Alice Updated"), (2, "Bob")),
        )
    ],
    ids=["upserts rows on unique key conflict using ON CONFLICT DO UPDATE"],
)
def test_given_merge_sql_when_merging_then_postgres_upserts_via_on_conflict(
    test_case: PostgresMergeTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    recorder: StatementRecorder = build_statement_recorder()
    target: str = qualified_name(schema=postgres_schema, name=test_case.table_name)
    adapter.execute(
        connection,
        f"CREATE TABLE {target} (id INTEGER PRIMARY KEY, name VARCHAR)",
    )
    adapter.execute(connection, f"INSERT INTO {target} {test_case.initial_sql}")

    adapter.merge(
        connection,
        target=target,
        sql=test_case.merge_sql,
        unique_key=test_case.unique_key,
        statement_recorder=recorder,
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, name FROM {target} ORDER BY id",
    )
    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresRowDiffTestCase(
            description="detects one mismatched row between left and right",
            left_sql="SELECT 1 AS id, 100 AS amount UNION ALL SELECT 2, 200",
            right_sql="SELECT 1 AS id, 100 AS amount UNION ALL SELECT 2, 999",
            unique_key=("id",),
            expected_result=RowDiffResult(
                left_count=2,
                right_count=2,
                joined_count=2,
                equal_count=1,
                unequal_count=1,
                left_only_count=0,
                right_only_count=0,
            ),
        )
    ],
    ids=["detects one mismatched row between left and right"],
)
def test_given_two_relations_when_diffing_rows_then_postgres_returns_diff_counts(
    test_case: PostgresRowDiffTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    left: str = qualified_name(schema=postgres_schema, name="left_rel")
    right: str = qualified_name(schema=postgres_schema, name="right_rel")
    adapter.execute(connection, f"CREATE TABLE {left} AS {test_case.left_sql}")
    adapter.execute(connection, f"CREATE TABLE {right} AS {test_case.right_sql}")

    result: RowDiffResult = adapter.diff_rows(
        connection,
        left=left,
        right=right,
        unique_key=test_case.unique_key,
    )

    assert result.left_count == test_case.expected_result.left_count
    assert result.right_count == test_case.expected_result.right_count
    assert result.equal_count == test_case.expected_result.equal_count
    assert result.unequal_count == test_case.expected_result.unequal_count
    assert result.left_only_count == test_case.expected_result.left_only_count
    assert result.right_only_count == test_case.expected_result.right_only_count


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresRowDiffSampleTestCase(
            description="samples the mismatched row with left and right values",
            left_sql="SELECT 1 AS id, 100 AS amount",
            right_sql="SELECT 1 AS id, 999 AS amount",
            unique_key=("id",),
            expected_unequal_rows=(
                RowDiffSampleRow(
                    key_values=(("id", 1),),
                    changed_cells=(
                        RowDiffSampleCell(name="amount", left_value=100, right_value=999),
                    ),
                ),
            ),
        )
    ],
    ids=["samples the mismatched row with left and right values"],
)
def test_given_mismatched_rows_when_sampling_then_postgres_returns_changed_cells(
    test_case: PostgresRowDiffSampleTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    left: str = qualified_name(schema=postgres_schema, name="left_rel")
    right: str = qualified_name(schema=postgres_schema, name="right_rel")
    adapter.execute(connection, f"CREATE TABLE {left} AS {test_case.left_sql}")
    adapter.execute(connection, f"CREATE TABLE {right} AS {test_case.right_sql}")

    samples: tuple[RowDiffSampleRow, ...] = adapter.sample_unequal_rows(
        connection,
        left=left,
        right=right,
        unique_key=test_case.unique_key,
    )

    assert len(samples) == len(test_case.expected_unequal_rows)
    for sample, expected in zip(samples, test_case.expected_unequal_rows, strict=True):
        assert sample.key_values == expected.key_values
        assert sample.changed_cells == expected.changed_cells


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresSchemaDiffTestCase(
            description="detects added and removed columns between two tables",
            left_ddl="CREATE TABLE {target} (id INTEGER, name VARCHAR)",
            right_ddl="CREATE TABLE {target} (id INTEGER, email VARCHAR)",
            expected_result=SchemaDiffResult(
                added_columns=(ColumnInfo(name="email", type="character varying"),),
                removed_columns=(ColumnInfo(name="name", type="character varying"),),
            ),
        )
    ],
    ids=["detects added and removed columns between two tables"],
)
def test_given_two_tables_when_diffing_schema_then_postgres_detects_column_changes(
    test_case: PostgresSchemaDiffTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    left: str = qualified_name(schema=postgres_schema, name="left_rel")
    right: str = qualified_name(schema=postgres_schema, name="right_rel")
    adapter.execute(connection, test_case.left_ddl.format(target=left))
    adapter.execute(connection, test_case.right_ddl.format(target=right))

    result: SchemaDiffResult = adapter.diff_schema(connection, left=left, right=right)

    assert result.added_columns == test_case.expected_result.added_columns
    assert result.removed_columns == test_case.expected_result.removed_columns


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresSeedTestCase(
            description="inserts all CSV rows into the target table",
            csv_text='id,name\n1,"Liege waffle"\n2,Stroopwafel\n',
            expected_rows=((1, "Liege waffle"), (2, "Stroopwafel")),
        )
    ],
    ids=["inserts all CSV rows into the target table"],
)
def test_given_seed_csv_when_loading_then_postgres_inserts_all_rows(
    test_case: PostgresSeedTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
    tmp_path: Path,
) -> None:
    target: str = qualified_name(schema=postgres_schema, name="waffle_types")
    seed_file: Path = write_seed_file(
        tmp_path=tmp_path,
        filename="waffle_types.csv",
        contents=test_case.csv_text,
    )

    adapter.load_seed(
        connection,
        target=target,
        file_path=seed_file,
        columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        statement_recorder=build_statement_recorder(),
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, name FROM {target} ORDER BY id",
    )
    assert rows == test_case.expected_rows
