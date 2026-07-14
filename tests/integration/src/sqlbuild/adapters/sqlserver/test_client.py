from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.models import ColumnInfo, QueryResult
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.executor.run.helpers.reuse.core import create_relation_from_reuse_origin
from tests.integration.src.sqlbuild.adapters.sqlserver._test_types import (
    SqlServerBuildFlowTestCase,
    SqlServerMergeTestCase,
    SqlServerQueryTestCase,
    SqlServerRelationReuseCopyTestCase,
    SqlServerSchemaIntrospectionTestCase,
    SqlServerSeedTestCase,
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
        SqlServerRelationReuseCopyTestCase(
            description="hard copy reuse uses select into fallback",
            expected_rows=((1, "alice"), (2, "bob")),
            expected_recorded_fragment="SELECT * INTO",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_origin_when_creating_hard_copy_then_sqlserver_copies_rows(
    test_case: SqlServerRelationReuseCopyTestCase,
    adapter: SqlServerAdapter,
    connection: Any,
    sqlserver_schema: str,
) -> None:
    origin: str = qualified_name(schema=sqlserver_schema, name="orders_reuse_origin")
    destination: str = qualified_name(schema=sqlserver_schema, name="orders_hard_reuse")
    recorder: StatementRecorder = build_statement_recorder()
    adapter.execute(
        connection=connection,
        sql=f"SELECT * INTO {origin} FROM "
        "(SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2, 'bob') AS origin_rows",
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
