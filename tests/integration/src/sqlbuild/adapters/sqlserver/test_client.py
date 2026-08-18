from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.constants import DIFF_LEFT_SIDE, DIFF_RIGHT_SIDE
from sqlbuild.adapter.contract.models import (
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
)
from sqlbuild.adapter.contract.types import CursorKind
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.integration.src.sqlbuild.adapters.sqlserver._test_types import (
    SqlServerBuildFlowTestCase,
    SqlServerMergeTestCase,
    SqlServerQueryTestCase,
    SqlServerRollbackPreservationTestCase,
    SqlServerRowDiffErrorTestCase,
    SqlServerRowDiffSamplingTestCase,
    SqlServerRowDiffTestCase,
    SqlServerSchemaDiffTestCase,
    SqlServerSchemaIntrospectionTestCase,
    SqlServerSeedTestCase,
    SqlServerTimestampCursorBoundTestCase,
)
from tests.integration.src.sqlbuild.adapters.sqlserver.helpers import (
    build_statement_recorder,
    fetch_rows,
    qualified_name,
    write_seed_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSchemaIntrospectionTestCase(
            description="describes columns in ordinal position order",
            table_name="orders",
            ddl="CREATE TABLE {target} (id INT, total DECIMAL(10,2), created_at DATETIME2)",
            expected_columns=(
                ColumnInfo(name="id", type="int"),
                ColumnInfo(name="total", type="decimal"),
                ColumnInfo(name="created_at", type="datetime2"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_when_describing_then_sqlserver_returns_columns_in_order(
    test_case: SqlServerSchemaIntrospectionTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    target: str = qualified_name(schema=sqlserver_schema, name=test_case.table_name)
    adapter.execute(connection=connection, sql=test_case.ddl.format(target=target))

    columns: tuple[ColumnInfo, ...] = adapter.describe_relation(
        connection=connection, relation=target
    )

    assert columns == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerQueryTestCase(
            description="returns inline query result with column names and rows",
            sql="SELECT 1 AS id, 'hello' AS name",
            expected_result=QueryResult(columns=("id", "name"), rows=((1, "hello"),)),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_when_querying_then_sqlserver_returns_named_rows(
    test_case: SqlServerQueryTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
) -> None:
    result: QueryResult = adapter.query(connection=connection, sql=test_case.sql, limit=None)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerBuildFlowTestCase(
            description="creates table from query and promotes via swap",
            table_name="fact_orders",
            source_sql="SELECT 1 AS id UNION ALL SELECT 2 UNION ALL SELECT 3",
            expected_row_count=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_sql_when_building_then_sqlserver_creates_and_promotes_table(
    test_case: SqlServerBuildFlowTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    recorder: StatementRecorder = build_statement_recorder()
    target: str = qualified_name(schema=sqlserver_schema, name=test_case.table_name)
    staging: str = qualified_name(schema=sqlserver_schema, name=f"{test_case.table_name}__staging")

    adapter.create_table_as(
        connection=connection,
        destination=staging,
        sql=test_case.source_sql,
        statement_recorder=recorder,
    )
    adapter.create_table_as(
        connection=connection,
        destination=target,
        sql=f"SELECT * FROM {staging}",
        statement_recorder=recorder,
    )
    adapter.swap(connection=connection, left=target, right=staging, statement_recorder=recorder)

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=connection, sql=f"SELECT COUNT(*) FROM {target}"
    )
    assert rows[0][0] == test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerMergeTestCase(
            description="upserts rows without requiring a database unique constraint",
            table_name="customers",
            initial_sql="SELECT 1 AS id, 'Alice' AS name",
            merge_sql="SELECT 1 AS id, 'Alice Updated' AS name UNION ALL SELECT 2, 'Bob'",
            unique_key=("id",),
            expected_rows=((1, "Alice Updated"), (2, "Bob")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_merge_sql_when_merging_then_sqlserver_upserts_without_constraint(
    test_case: SqlServerMergeTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    recorder: StatementRecorder = build_statement_recorder()
    target: str = qualified_name(schema=sqlserver_schema, name=test_case.table_name)
    adapter.execute(
        connection=connection, sql=f"CREATE TABLE {target} (id INT, name NVARCHAR(100))"
    )
    adapter.execute(connection=connection, sql=f"INSERT INTO {target} {test_case.initial_sql}")

    adapter.merge(
        connection=connection,
        destination=target,
        sql=test_case.merge_sql,
        unique_key=test_case.unique_key,
        statement_recorder=recorder,
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=connection, sql=f"SELECT id, name FROM {target} ORDER BY id"
    )
    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSeedTestCase(
            description="inserts all CSV rows into the target table",
            csv_text='id,name\n1,"Liege waffle"\n2,Stroopwafel\n',
            expected_rows=((1, "Liege waffle"), (2, "Stroopwafel")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_csv_when_loading_then_sqlserver_inserts_all_rows(
    test_case: SqlServerSeedTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
    tmp_path: Path,
) -> None:
    seed_file: Path = write_seed_file(tmp_path, test_case.csv_text)
    target: str = qualified_name(schema=sqlserver_schema, name="waffle_types")

    adapter.load_seed(
        connection=connection,
        destination=target,
        file_path=seed_file,
        columns=(ColumnInfo(name="id", type="INT"), ColumnInfo(name="name", type="NVARCHAR(100)")),
        replace=True,
        statement_recorder=build_statement_recorder(),
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter, connection=connection, sql=f"SELECT id, name FROM {target} ORDER BY id"
    )
    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerRollbackPreservationTestCase(
            description="preserves the original error after sqlserver already rolled back",
            original_error_message="original transaction failure",
            expected_transaction_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ended_transaction_when_context_raises_then_original_error_is_preserved(
    test_case: SqlServerRollbackPreservationTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
) -> None:
    with pytest.raises(RuntimeError, match=test_case.original_error_message):
        with adapter.transaction(connection):
            adapter.execute(connection=connection, sql="ROLLBACK TRANSACTION")
            raise RuntimeError(test_case.original_error_message)

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql="SELECT @@TRANCOUNT",
    )
    assert int(str(rows[0][0])) == test_case.expected_transaction_count


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerTimestampCursorBoundTestCase(
            description="deletes legacy datetime values with fractional datetime2 bounds",
            cursor_start="2026-04-04T14:30:00",
            cursor_end="2026-04-04T14:30:00.000001",
            expected_rows=((2,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_legacy_datetime_when_deleting_fractional_bounds_then_sqlserver_accepts_them(
    test_case: SqlServerTimestampCursorBoundTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    target: str = qualified_name(schema=sqlserver_schema, name="timestamp_events")
    adapter.execute(
        connection=connection,
        sql=f"CREATE TABLE {target} (event_id INT, ordered_at DATETIME)",
    )
    adapter.execute(
        connection=connection,
        sql=f"INSERT INTO {target} VALUES (1, '2026-04-04T14:30:00')",
    )
    adapter.delete_insert_cursor(
        connection=connection,
        destination=target,
        sql="SELECT 2 AS event_id, CAST('2026-04-04T14:30:00' AS DATETIME) AS ordered_at",
        cursor_column="ordered_at",
        cursor_start=test_case.cursor_start,
        cursor_end=test_case.cursor_end,
        statement_recorder=build_statement_recorder(),
        cursor_type=CursorKind.TIMESTAMP,
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT event_id FROM {target}",
    )

    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    (
        SqlServerSchemaDiffTestCase(
            description="detects added removed and type-changed columns",
            left_ddl="CREATE TABLE {target} (id INT, status NVARCHAR(20), old_col BIT)",
            right_ddl="CREATE TABLE {target} (id BIGINT, status NVARCHAR(20), new_col DATE)",
            expected_result=SchemaDiffResult(
                added_columns=(ColumnInfo(name="new_col", type="date NULL"),),
                removed_columns=(ColumnInfo(name="old_col", type="bit NULL"),),
                type_changed_columns=(
                    (
                        ColumnInfo(name="id", type="int NULL"),
                        ColumnInfo(name="id", type="bigint NULL"),
                    ),
                ),
            ),
        ),
        SqlServerSchemaDiffTestCase(
            description="preserves precision length and nullability in changed types",
            left_ddl=(
                "CREATE TABLE {target} ("
                "id INT NOT NULL, amount DECIMAL(10,2), label NVARCHAR(20) NULL)"
            ),
            right_ddl=(
                "CREATE TABLE {target} ("
                "id INT NOT NULL, amount DECIMAL(12,3), label NVARCHAR(20) NOT NULL)"
            ),
            expected_result=SchemaDiffResult(
                type_changed_columns=(
                    (
                        ColumnInfo(name="amount", type="decimal(10,2) NULL"),
                        ColumnInfo(name="amount", type="decimal(12,3) NULL"),
                    ),
                    (
                        ColumnInfo(name="label", type="nvarchar(20) NULL"),
                        ColumnInfo(name="label", type="nvarchar(20) NOT NULL"),
                    ),
                ),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_tables_when_diffing_schema_then_sqlserver_detects_column_changes(
    test_case: SqlServerSchemaDiffTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    left: str = qualified_name(schema=sqlserver_schema, name="schema_diff_left")
    right: str = qualified_name(schema=sqlserver_schema, name="schema_diff_right")
    adapter.execute(connection=connection, sql=test_case.left_ddl.format(target=left))
    adapter.execute(connection=connection, sql=test_case.right_ddl.format(target=right))

    result: SchemaDiffResult = adapter.diff_schema(connection=connection, left=left, right=right)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (
        SqlServerRowDiffTestCase(
            description="detects equal unequal and side-only rows",
            left_ddl=(
                "CREATE TABLE {target} (id INT, status NVARCHAR(20), amount INT); "
                "INSERT INTO {target} VALUES (1, 'same', 100), (2, 'before', 200), "
                "(3, 'left', 300), (5, 'nullable', NULL)"
            ),
            right_ddl=(
                "CREATE TABLE {target} (id INT, status NVARCHAR(20), amount INT); "
                "INSERT INTO {target} VALUES (1, 'same', 100), (2, 'after', 202), "
                "(4, 'right', 400), (5, 'nullable', NULL)"
            ),
            unique_key=("id",),
            expected_result=RowDiffResult(
                left_count=4,
                right_count=4,
                joined_count=5,
                equal_count=2,
                unequal_count=1,
                left_only_count=1,
                right_only_count=1,
                column_results=(
                    RowDiffColumnResult(name="status", mismatched_count=1),
                    RowDiffColumnResult(name="amount", mismatched_count=1),
                ),
            ),
        ),
        SqlServerRowDiffTestCase(
            description="limits row comparison to integer cursor bounds",
            left_ddl=(
                "CREATE TABLE {target} (id INT, status NVARCHAR(20)); "
                "INSERT INTO {target} VALUES (1, 'outside-left'), (2, 'same'), (3, 'same')"
            ),
            right_ddl=(
                "CREATE TABLE {target} (id INT, status NVARCHAR(20)); "
                "INSERT INTO {target} VALUES (1, 'outside-right'), (2, 'same'), (3, 'same')"
            ),
            unique_key=("id",),
            cursor_column="id",
            start_cursor=CursorValue(kind=CursorKind.INTEGER, value=2),
            end_cursor=CursorValue(kind=CursorKind.INTEGER, value=4),
            expected_result=RowDiffResult(
                left_count=2,
                right_count=2,
                joined_count=2,
                equal_count=2,
                unequal_count=0,
                left_only_count=0,
                right_only_count=0,
                column_results=(RowDiffColumnResult(name="status", mismatched_count=0),),
            ),
        ),
        SqlServerRowDiffTestCase(
            description="limits row comparison to timestamp cursor bounds",
            left_ddl=(
                "CREATE TABLE {target} (id INT, ordered_at DATETIME2, status NVARCHAR(20)); "
                "INSERT INTO {target} VALUES "
                "(1, '2026-04-01T09:00:00', 'outside-left'), "
                "(2, '2026-04-02T09:00:00', 'same'), "
                "(3, '2026-04-03T09:00:00', 'outside-left')"
            ),
            right_ddl=(
                "CREATE TABLE {target} (id INT, ordered_at DATETIME2, status NVARCHAR(20)); "
                "INSERT INTO {target} VALUES "
                "(1, '2026-04-01T09:00:00', 'outside-right'), "
                "(2, '2026-04-02T09:00:00', 'same'), "
                "(3, '2026-04-03T09:00:00', 'outside-right')"
            ),
            unique_key=("id",),
            cursor_column="ordered_at",
            start_cursor=CursorValue(
                kind=CursorKind.TIMESTAMP,
                value=datetime.fromisoformat("2026-04-02T00:00:00"),
            ),
            end_cursor=CursorValue(
                kind=CursorKind.TIMESTAMP,
                value=datetime.fromisoformat("2026-04-03T00:00:00"),
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
                    RowDiffColumnResult(name="ordered_at", mismatched_count=0),
                    RowDiffColumnResult(name="status", mismatched_count=0),
                ),
            ),
        ),
        SqlServerRowDiffTestCase(
            description="applies absolute numeric tolerance",
            left_ddl=(
                "CREATE TABLE {target} (id INT, amount DECIMAL(10,3)); "
                "INSERT INTO {target} VALUES (1, 100.000)"
            ),
            right_ddl=(
                "CREATE TABLE {target} (id INT, amount DECIMAL(10,3)); "
                "INSERT INTO {target} VALUES (1, 100.005)"
            ),
            unique_key=("id",),
            tolerances=RowDiffTolerances(
                by_column={"amount": RowDiffTolerance(absolute=Decimal("0.01"))}
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
        SqlServerRowDiffTestCase(
            description="applies relative numeric tolerance",
            left_ddl=(
                "CREATE TABLE {target} (id INT, metric FLOAT); "
                "INSERT INTO {target} VALUES (1, 1000000.0)"
            ),
            right_ddl=(
                "CREATE TABLE {target} (id INT, metric FLOAT); "
                "INSERT INTO {target} VALUES (1, 1000050.0)"
            ),
            unique_key=("id",),
            tolerances=RowDiffTolerances(
                by_column={"metric": RowDiffTolerance(relative=Decimal("0.0001"))}
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
                        name="metric",
                        mismatched_count=0,
                        tolerance=RowDiffTolerance(relative=Decimal("0.0001")),
                    ),
                ),
            ),
        ),
        SqlServerRowDiffTestCase(
            description="treats null and non-null values as unequal",
            left_ddl=(
                "CREATE TABLE {target} (id INT, amount INT); INSERT INTO {target} VALUES (1, NULL)"
            ),
            right_ddl=(
                "CREATE TABLE {target} (id INT, amount INT); INSERT INTO {target} VALUES (1, 5)"
            ),
            unique_key=("id",),
            expected_result=RowDiffResult(
                left_count=1,
                right_count=1,
                joined_count=1,
                equal_count=0,
                unequal_count=1,
                left_only_count=0,
                right_only_count=0,
                column_results=(RowDiffColumnResult(name="amount", mismatched_count=1),),
            ),
        ),
        SqlServerRowDiffTestCase(
            description="joins rows on composite unique keys",
            left_ddl=(
                "CREATE TABLE {target} (order_id INT, line_number INT, status NVARCHAR(20)); "
                "INSERT INTO {target} VALUES (1, 1, 'same'), (1, 2, 'before')"
            ),
            right_ddl=(
                "CREATE TABLE {target} (order_id INT, line_number INT, status NVARCHAR(20)); "
                "INSERT INTO {target} VALUES (1, 1, 'same'), (1, 2, 'after')"
            ),
            unique_key=("order_id", "line_number"),
            expected_result=RowDiffResult(
                left_count=2,
                right_count=2,
                joined_count=2,
                equal_count=1,
                unequal_count=1,
                left_only_count=0,
                right_only_count=0,
                column_results=(RowDiffColumnResult(name="status", mismatched_count=1),),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_tables_when_diffing_rows_then_sqlserver_returns_expected_counts(
    test_case: SqlServerRowDiffTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    left: str = qualified_name(schema=sqlserver_schema, name="row_diff_left")
    right: str = qualified_name(schema=sqlserver_schema, name="row_diff_right")
    adapter.execute(connection=connection, sql=test_case.left_ddl.format(target=left))
    adapter.execute(connection=connection, sql=test_case.right_ddl.format(target=right))

    result: RowDiffResult = adapter.diff_rows(
        connection=connection,
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


@pytest.mark.parametrize(
    "test_case",
    (
        SqlServerRowDiffSamplingTestCase(
            description="returns deterministic changed and side-only samples",
            expected_unequal_rows=(
                RowDiffSampleRow(
                    key_values=(("id", 2),),
                    changed_cells=(
                        RowDiffSampleCell(
                            name="status",
                            left_value="before",
                            right_value="after",
                        ),
                    ),
                ),
            ),
            expected_left_only_rows=((("id", 3),),),
            expected_right_only_rows=((("id", 4),),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_changed_and_side_only_rows_when_sampling_then_sqlserver_returns_keys_and_cells(
    test_case: SqlServerRowDiffSamplingTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    left: str = qualified_name(schema=sqlserver_schema, name="sample_diff_left")
    right: str = qualified_name(schema=sqlserver_schema, name="sample_diff_right")
    adapter.execute(
        connection=connection,
        sql=f"CREATE TABLE {left} (id INT, status NVARCHAR(20), amount DECIMAL(10,3)); "
        f"INSERT INTO {left} VALUES "
        "(1, 'same', 50.000), (2, 'before', 100.000), (3, 'left', 300.000)",
    )
    adapter.execute(
        connection=connection,
        sql=f"CREATE TABLE {right} (id INT, status NVARCHAR(20), amount DECIMAL(10,3)); "
        f"INSERT INTO {right} VALUES "
        "(1, 'same', 50.000), (2, 'after', 100.005), (4, 'right', 400.000)",
    )

    unequal_rows: tuple[RowDiffSampleRow, ...] = adapter.sample_unequal_rows(
        connection=connection,
        left=left,
        right=right,
        unique_key=("id",),
        tolerances=RowDiffTolerances(
            by_column={"amount": RowDiffTolerance(absolute=Decimal("0.01"))}
        ),
        limit=1,
    )
    left_only_rows: tuple[tuple[tuple[str, object], ...], ...] = adapter.sample_side_only_rows(
        connection=connection,
        left=left,
        right=right,
        unique_key=("id",),
        side=DIFF_LEFT_SIDE,
        limit=1,
    )
    right_only_rows: tuple[tuple[tuple[str, object], ...], ...] = adapter.sample_side_only_rows(
        connection=connection,
        left=left,
        right=right,
        unique_key=("id",),
        side=DIFF_RIGHT_SIDE,
        limit=1,
    )

    assert unequal_rows == test_case.expected_unequal_rows
    assert left_only_rows == test_case.expected_left_only_rows
    assert right_only_rows == test_case.expected_right_only_rows


@pytest.mark.parametrize(
    "test_case",
    (
        SqlServerRowDiffErrorTestCase(
            description="rejects non-comparable XML columns",
            column_name="payload",
            column_type="XML",
            value_sql="'<value>one</value>'",
            expected_error_fragment=(
                "row diff column 'payload' uses unsupported SQL Server comparison type 'xml'"
            ),
        ),
        SqlServerRowDiffErrorTestCase(
            description="rejects numeric tolerance on text columns",
            column_name="status",
            column_type="NVARCHAR(20)",
            value_sql="'ready'",
            tolerances=RowDiffTolerances(
                by_column={"status": RowDiffTolerance(absolute=Decimal("1"))}
            ),
            expected_error_fragment=(
                "row diff tolerance for non-numeric column 'status' is invalid"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_comparison_when_diffing_then_sqlserver_reports_column_error(
    test_case: SqlServerRowDiffErrorTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    left: str = qualified_name(schema=sqlserver_schema, name="invalid_diff_left")
    right: str = qualified_name(schema=sqlserver_schema, name="invalid_diff_right")
    for relation in (left, right):
        adapter.execute(
            connection=connection,
            sql=f"CREATE TABLE {relation} (id INT, {test_case.column_name} "
            f"{test_case.column_type}); INSERT INTO {relation} VALUES (1, "
            f"{test_case.value_sql})",
        )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        adapter.diff_rows(
            connection=connection,
            left=left,
            right=right,
            unique_key=("id",),
            tolerances=test_case.tolerances,
        )
