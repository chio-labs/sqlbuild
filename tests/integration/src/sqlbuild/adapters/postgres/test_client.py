from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    QueryResult,
    RowDiffColumnResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    RowDiffTolerance,
    RowDiffTolerances,
    SchemaDiffResult,
    StatementRecorder,
)
from sqlbuild.adapter.shared.types import CursorKind
from sqlbuild.adapters.postgres.client import PostgresAdapter
from sqlbuild.executor.run.helpers.reuse import create_relation_from_reuse_origin
from tests.integration.src.sqlbuild.adapters.postgres._test_types import (
    PostgresBuildFlowTestCase,
    PostgresCountRowsTestCase,
    PostgresMergeTestCase,
    PostgresQueryTestCase,
    PostgresRelationReuseCopyTestCase,
    PostgresRowDiffErrorTestCase,
    PostgresRowDiffSampleTestCase,
    PostgresRowDiffTestCase,
    PostgresSchemaDiffTestCase,
    PostgresSchemaIntrospectionTestCase,
    PostgresSeedTestCase,
)
from tests.integration.src.sqlbuild.adapters.postgres.helpers import (
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
        connection, destination=staging, sql=test_case.source_sql, statement_recorder=recorder
    )
    adapter.create_table_as(
        connection, destination=target, sql=f"SELECT * FROM {staging}", statement_recorder=recorder
    )
    adapter.swap(connection, left=target, right=staging, statement_recorder=recorder)

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=connection, sql=f"SELECT COUNT(*) FROM {target}"
    )
    assert rows[0][0] == test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresRelationReuseCopyTestCase(
            description="hard copy reuse uses CTAS fallback",
            expected_rows=((1, "alice"), (2, "bob")),
            expected_recorded_fragment=" AS SELECT * FROM ",
        )
    ],
    ids=["hard copy reuse uses CTAS fallback"],
)
def test_given_reuse_origin_when_creating_hard_copy_then_postgres_copies_rows(
    test_case: PostgresRelationReuseCopyTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    origin: str = qualified_name(schema=postgres_schema, name="orders_reuse_origin")
    destination: str = qualified_name(schema=postgres_schema, name="orders_hard_reuse")
    recorder: StatementRecorder = build_statement_recorder()
    adapter.execute(
        connection,
        f"CREATE TABLE {origin} AS SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2, 'bob'",
    )

    create_relation_from_reuse_origin(
        adapter=adapter,
        connection=connection,
        origin_relation=origin,
        destination_relation=destination,
        hard_copy=True,
        statement_recorder=recorder,
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, name FROM {destination} ORDER BY id",
    )
    recorded_sql: str = "\n".join(event.content for event in recorder.snapshot())

    assert rows == test_case.expected_rows
    assert test_case.expected_recorded_fragment in recorded_sql


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresMergeTestCase(
            description="upserts rows without requiring a database unique constraint",
            table_name="customers",
            initial_sql="SELECT 1 AS id, 'Alice' AS name",
            merge_sql="SELECT 1 AS id, 'Alice Updated' AS name UNION ALL SELECT 2, 'Bob'",
            unique_key=("id",),
            expected_rows=((1, "Alice Updated"), (2, "Bob")),
        )
    ],
    ids=["upserts rows without requiring a database unique constraint"],
)
def test_given_merge_sql_when_merging_then_postgres_upserts_without_constraint(
    test_case: PostgresMergeTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    recorder: StatementRecorder = build_statement_recorder()
    target: str = qualified_name(schema=postgres_schema, name=test_case.table_name)
    adapter.execute(
        connection,
        f"CREATE TABLE {target} (id INTEGER, name VARCHAR)",
    )
    adapter.execute(connection, f"INSERT INTO {target} {test_case.initial_sql}")

    adapter.merge(
        connection,
        destination=target,
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


ROW_DIFF_TEST_CASES: list[PostgresRowDiffTestCase] = [
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
            column_results=(RowDiffColumnResult(name="amount", mismatched_count=1),),
        ),
    ),
    PostgresRowDiffTestCase(
        description="counts equal rows for identical tables",
        left_sql="SELECT 1 AS id, 10 AS amount",
        right_sql="SELECT 1 AS id, 10 AS amount",
        unique_key=("id",),
        expected_result=RowDiffResult(
            left_count=1,
            right_count=1,
            joined_count=1,
            equal_count=1,
            unequal_count=0,
            left_only_count=0,
            right_only_count=0,
            column_results=(RowDiffColumnResult(name="amount", mismatched_count=0),),
        ),
    ),
    PostgresRowDiffTestCase(
        description="detects equal unequal and side-only rows across three rows",
        left_sql=("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2, 'b' UNION ALL SELECT 3, 'c'"),
        right_sql=("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2, 'x' UNION ALL SELECT 4, 'd'"),
        unique_key=("id",),
        expected_result=RowDiffResult(
            left_count=3,
            right_count=3,
            joined_count=4,
            equal_count=1,
            unequal_count=1,
            left_only_count=1,
            right_only_count=1,
            column_results=(RowDiffColumnResult(name="val", mismatched_count=1),),
        ),
    ),
    PostgresRowDiffTestCase(
        description="excludes columns from comparison",
        left_sql="SELECT 1 AS id, 'a' AS val, 'ignore1' AS extra",
        right_sql="SELECT 1 AS id, 'a' AS val, 'ignore2' AS extra",
        unique_key=("id",),
        excluded_columns=("extra",),
        expected_result=RowDiffResult(
            left_count=1,
            right_count=1,
            joined_count=1,
            equal_count=1,
            unequal_count=0,
            left_only_count=0,
            right_only_count=0,
            column_results=(RowDiffColumnResult(name="val", mismatched_count=0),),
        ),
    ),
    PostgresRowDiffTestCase(
        description="treats values within absolute tolerance as equal",
        left_sql="SELECT 1 AS id, CAST(100.00 AS NUMERIC) AS amount",
        right_sql="SELECT 1 AS id, CAST(100.005 AS NUMERIC) AS amount",
        unique_key=("id",),
        tolerances=RowDiffTolerances(
            by_column={"amount": RowDiffTolerance(absolute=Decimal("0.01"))},
        ),
        expected_result=RowDiffResult(
            left_count=1,
            right_count=1,
            joined_count=1,
            equal_count=1,
            unequal_count=0,
            left_only_count=0,
            right_only_count=0,
            column_results=(
                RowDiffColumnResult(
                    name="amount",
                    mismatched_count=0,
                    tolerance=RowDiffTolerance(absolute=Decimal("0.01")),
                ),
            ),
        ),
    ),
    PostgresRowDiffTestCase(
        description="reports numeric difference outside absolute tolerance",
        left_sql="SELECT 1 AS id, CAST(100.00 AS NUMERIC) AS amount",
        right_sql="SELECT 1 AS id, CAST(100.02 AS NUMERIC) AS amount",
        unique_key=("id",),
        tolerances=RowDiffTolerances(
            by_column={"amount": RowDiffTolerance(absolute=Decimal("0.01"))},
        ),
        expected_result=RowDiffResult(
            left_count=1,
            right_count=1,
            joined_count=1,
            equal_count=0,
            unequal_count=1,
            left_only_count=0,
            right_only_count=0,
            column_results=(
                RowDiffColumnResult(
                    name="amount",
                    mismatched_count=1,
                    tolerance=RowDiffTolerance(absolute=Decimal("0.01")),
                ),
            ),
        ),
    ),
    PostgresRowDiffTestCase(
        description="filters rows by integer cursor bounds",
        left_sql=("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2, 'b' UNION ALL SELECT 3, 'c'"),
        right_sql=("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2, 'b' UNION ALL SELECT 3, 'c'"),
        unique_key=("id",),
        cursor_column="id",
        start_cursor=CursorValue(kind=CursorKind.INTEGER, value=2),
        end_cursor=CursorValue(kind=CursorKind.INTEGER, value=3),
        expected_result=RowDiffResult(
            left_count=1,
            right_count=1,
            joined_count=1,
            equal_count=1,
            unequal_count=0,
            left_only_count=0,
            right_only_count=0,
            column_results=(RowDiffColumnResult(name="val", mismatched_count=0),),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ROW_DIFF_TEST_CASES,
    ids=[case.description for case in ROW_DIFF_TEST_CASES],
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
        excluded_columns=test_case.excluded_columns,
        tolerances=test_case.tolerances,
        cursor_column=test_case.cursor_column,
        start_cursor=test_case.start_cursor,
        end_cursor=test_case.end_cursor,
    )

    assert result == test_case.expected_result


ROW_DIFF_ERROR_TEST_CASES: list[PostgresRowDiffErrorTestCase] = [
    PostgresRowDiffErrorTestCase(
        description="rejects duplicate unique key in left relation",
        left_sql="SELECT 1 AS id, 'a' AS val UNION ALL SELECT 1, 'b'",
        right_sql="SELECT 1 AS id, 'a' AS val",
        unique_key=("id",),
        expected_error_fragment="left relation contains duplicate unique_key values",
    ),
    PostgresRowDiffErrorTestCase(
        description="rejects duplicate unique key in right relation",
        left_sql="SELECT 1 AS id, 'a' AS val",
        right_sql="SELECT 1 AS id, 'a' AS val UNION ALL SELECT 1, 'b'",
        unique_key=("id",),
        expected_error_fragment="right relation contains duplicate unique_key values",
    ),
    PostgresRowDiffErrorTestCase(
        description="rejects tolerance for non-numeric column",
        left_sql="SELECT 1 AS id, 'a' AS status",
        right_sql="SELECT 1 AS id, 'b' AS status",
        unique_key=("id",),
        tolerances=RowDiffTolerances(
            by_column={"status": RowDiffTolerance(absolute=Decimal("1"))},
        ),
        expected_error_fragment="row diff tolerance for non-numeric column 'status' is invalid",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ROW_DIFF_ERROR_TEST_CASES,
    ids=[case.description for case in ROW_DIFF_ERROR_TEST_CASES],
)
def test_given_invalid_diff_when_diffing_rows_then_postgres_raises_clear_error(
    test_case: PostgresRowDiffErrorTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    left: str = qualified_name(schema=postgres_schema, name="left_rel")
    right: str = qualified_name(schema=postgres_schema, name="right_rel")
    adapter.execute(connection, f"CREATE TABLE {left} AS {test_case.left_sql}")
    adapter.execute(connection, f"CREATE TABLE {right} AS {test_case.right_sql}")

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        adapter.diff_rows(
            connection,
            left=left,
            right=right,
            unique_key=test_case.unique_key,
            tolerances=test_case.tolerances,
        )


COUNT_ROWS_TEST_CASES: list[PostgresCountRowsTestCase] = [
    PostgresCountRowsTestCase(
        description="counts all rows without cursor filter",
        table_name="count_t",
        values_sql="(1), (2), (3)",
        expected_count=3,
    ),
    PostgresCountRowsTestCase(
        description="counts rows bounded by integer cursor",
        table_name="count_bounded",
        values_sql="(1), (2), (3), (4), (5)",
        cursor_column="id",
        start_cursor=CursorValue(kind=CursorKind.INTEGER, value=2),
        end_cursor=CursorValue(kind=CursorKind.INTEGER, value=4),
        expected_count=2,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    COUNT_ROWS_TEST_CASES,
    ids=[case.description for case in COUNT_ROWS_TEST_CASES],
)
def test_given_table_when_counting_rows_then_postgres_returns_expected_count(
    test_case: PostgresCountRowsTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    target: str = qualified_name(schema=postgres_schema, name=test_case.table_name)
    adapter.execute(connection, f"CREATE TABLE {target} (id INTEGER)")
    adapter.execute(connection, f"INSERT INTO {target} VALUES {test_case.values_sql}")

    count: int = adapter.count_rows(
        connection,
        relation=target,
        cursor_column=test_case.cursor_column,
        start_cursor=test_case.start_cursor,
        end_cursor=test_case.end_cursor,
    )

    assert count == test_case.expected_count


ROW_DIFF_SAMPLE_TEST_CASES: list[PostgresRowDiffSampleTestCase] = [
    PostgresRowDiffSampleTestCase(
        description="samples the mismatched row with left and right values",
        left_sql="SELECT 1 AS id, 100 AS amount",
        right_sql="SELECT 1 AS id, 999 AS amount",
        unique_key=("id",),
        expected_unequal_rows=(
            RowDiffSampleRow(
                key_values=(("id", 1),),
                changed_cells=(RowDiffSampleCell(name="amount", left_value=100, right_value=999),),
            ),
        ),
    ),
    PostgresRowDiffSampleTestCase(
        description="samples changed values for multiple mismatched rows",
        left_sql=("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val"),
        right_sql=("SELECT 1 AS id, 'x' AS val UNION ALL SELECT 2 AS id, 'b' AS val"),
        unique_key=("id",),
        expected_unequal_rows=(
            RowDiffSampleRow(
                key_values=(("id", 1),),
                changed_cells=(RowDiffSampleCell(name="val", left_value="a", right_value="x"),),
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ROW_DIFF_SAMPLE_TEST_CASES,
    ids=[case.description for case in ROW_DIFF_SAMPLE_TEST_CASES],
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


SIDE_ONLY_SAMPLE_TEST_CASES: list[PostgresRowDiffSampleTestCase] = [
    PostgresRowDiffSampleTestCase(
        description="returns left-only key samples",
        left_sql=("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val"),
        right_sql=("SELECT 2 AS id, 'b' AS val UNION ALL SELECT 3 AS id, 'c' AS val"),
        unique_key=("id",),
        side="left",
        expected_side_only_rows=((("id", 1),),),
    ),
    PostgresRowDiffSampleTestCase(
        description="returns right-only key samples",
        left_sql=("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val"),
        right_sql=("SELECT 2 AS id, 'b' AS val UNION ALL SELECT 3 AS id, 'c' AS val"),
        unique_key=("id",),
        side="right",
        expected_side_only_rows=((("id", 3),),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SIDE_ONLY_SAMPLE_TEST_CASES,
    ids=[case.description for case in SIDE_ONLY_SAMPLE_TEST_CASES],
)
def test_given_side_only_rows_when_sampling_then_postgres_returns_key_values(
    test_case: PostgresRowDiffSampleTestCase,
    adapter: PostgresAdapter,
    connection: Any,
    postgres_schema: str,
) -> None:
    left: str = qualified_name(schema=postgres_schema, name="left_rel")
    right: str = qualified_name(schema=postgres_schema, name="right_rel")
    adapter.execute(connection, f"CREATE TABLE {left} AS {test_case.left_sql}")
    adapter.execute(connection, f"CREATE TABLE {right} AS {test_case.right_sql}")

    side_only: tuple[tuple[tuple[str, object], ...], ...] = adapter.sample_side_only_rows(
        connection,
        left=left,
        right=right,
        unique_key=test_case.unique_key,
        side=test_case.side,
        limit=5,
    )

    assert side_only == test_case.expected_side_only_rows


SCHEMA_DIFF_TEST_CASES: list[PostgresSchemaDiffTestCase] = [
    PostgresSchemaDiffTestCase(
        description="detects added and removed columns between two tables",
        left_ddl="CREATE TABLE {target} (id INTEGER, name VARCHAR)",
        right_ddl="CREATE TABLE {target} (id INTEGER, email VARCHAR)",
        expected_result=SchemaDiffResult(
            added_columns=(ColumnInfo(name="email", type="character varying"),),
            removed_columns=(ColumnInfo(name="name", type="character varying"),),
        ),
    ),
    PostgresSchemaDiffTestCase(
        description="detects added removed and type-changed columns",
        left_ddl="CREATE TABLE {target} (id INTEGER, status TEXT, old_col BOOLEAN)",
        right_ddl="CREATE TABLE {target} (id BIGINT, status TEXT, new_col DATE)",
        expected_result=SchemaDiffResult(
            added_columns=(ColumnInfo(name="new_col", type="date"),),
            removed_columns=(ColumnInfo(name="old_col", type="boolean"),),
            type_changed_columns=(
                (
                    ColumnInfo(name="id", type="integer"),
                    ColumnInfo(name="id", type="bigint"),
                ),
            ),
        ),
    ),
    PostgresSchemaDiffTestCase(
        description="ignores equivalent type aliases such as NUMERIC and DECIMAL",
        left_ddl="CREATE TABLE {target} (id INTEGER, amount NUMERIC(10,2))",
        right_ddl="CREATE TABLE {target} (id INT4, amount DECIMAL(10,2))",
        expected_result=SchemaDiffResult(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SCHEMA_DIFF_TEST_CASES,
    ids=[case.description for case in SCHEMA_DIFF_TEST_CASES],
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
    assert result.type_changed_columns == test_case.expected_result.type_changed_columns


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
        destination=target,
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
