from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    CursorValue,
    ExpressionInferenceProfile,
    QueryResult,
    RowDiffColumnResult,
    RowDiffResult,
    RowDiffTolerance,
    RowDiffTolerances,
    SchemaDiffResult,
)
from sqlbuild.adapter.contract.types import CursorKind, FunctionNullabilityRule
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.contracts.models import SeedCsvSettings
from tests.integration.src.sqlbuild.adapters.duckdb._test_types import (
    ConnectSettingsTestCase,
    ConnectTestCase,
    CountRowsTestCase,
    DeleteInsertTestCase,
    DiffRowsErrorTestCase,
    DiffRowsTestCase,
    DiffSchemaTestCase,
    DropTestCase,
    ExpressionNullabilityRuleTestCase,
    GetAllColumnsTestCase,
    GetColumnsTestCase,
    ListRelationsTestCase,
    LoadSeedTestCase,
    MaterializeTestCase,
    MergeTestCase,
    QueryTestCase,
    RecorderWriteTestCase,
    RelationExistsTestCase,
    RenameTestCase,
    SwapTestCase,
    TransactionalAtomicityTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExpressionNullabilityRuleTestCase(
            description="LOWER preserves non-null literal",
            function_name="LOWER",
            sql_expression="LOWER('READY')",
            rule_args=(InferredNullability.NON_NULL,),
            expected_nullability=InferredNullability.NON_NULL,
            expected_is_null=False,
        ),
        ExpressionNullabilityRuleTestCase(
            description="LOWER preserves nullable input",
            function_name="LOWER",
            sql_expression="LOWER(CAST(NULL AS VARCHAR))",
            rule_args=(InferredNullability.NULLABLE,),
            expected_nullability=InferredNullability.NULLABLE,
            expected_is_null=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expression_rule_when_querying_then_duckdb_matches_nullability_expectation(
    test_case: ExpressionNullabilityRuleTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()
    rule: FunctionNullabilityRule | None = profile.function_nullability_rule(
        test_case.function_name
    )
    assert rule is not None

    result: QueryResult = adapter.query(
        connection=connection,
        sql=f"SELECT {test_case.sql_expression} IS NULL AS is_null",
        limit=None,
    )

    assert rule(test_case.rule_args) == test_case.expected_nullability
    assert result.rows == ((test_case.expected_is_null,),)


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectTestCase(
            description="connects with default in-memory database",
            config={},
            expected_connects=True,
        ),
        ConnectTestCase(
            description="connects with explicit memory database",
            config={"database": ":memory:"},
            expected_connects=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_config_when_connecting_then_returns_usable_connection(
    test_case: ConnectTestCase,
    adapter: DuckDbAdapter,
) -> None:
    connection: Any = adapter.connect(test_case.config)

    assert (connection is not None) == test_case.expected_connects
    adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectSettingsTestCase(
            description="applies settings from config",
            config={"database": ":memory:", "settings": {"threads": "1"}},
            expected_setting_value="1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_config_with_settings_when_connecting_then_applies_settings(
    test_case: ConnectSettingsTestCase,
    adapter: DuckDbAdapter,
) -> None:
    connection: Any = adapter.connect(test_case.config)
    result: Any = connection.execute("SELECT current_setting('threads')").fetchone()

    assert str(result[0]) == test_case.expected_setting_value
    adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        QueryTestCase(
            description="returns rows and marks limit truncation",
            sql="SELECT * FROM (VALUES (1, 'alice'), (2, 'bob')) AS t(id, name) ORDER BY id",
            limit=1,
            expected_result=QueryResult(
                columns=("id", "name"),
                rows=((1, "alice"),),
                truncated=True,
            ),
        ),
        QueryTestCase(
            description="returns all rows without limit",
            sql="SELECT * FROM (VALUES (1), (2)) AS t(id) ORDER BY id",
            limit=None,
            expected_result=QueryResult(columns=("id",), rows=((1,), (2,))),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_when_querying_then_returns_normalized_query_result(
    test_case: QueryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: QueryResult = adapter.query(
        connection=connection, sql=test_case.sql, limit=test_case.limit
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        RelationExistsTestCase(
            description="returns true for existing table",
            setup_sql=("CREATE TABLE test_table (id INTEGER)",),
            database=None,
            schema=None,
            name="test_table",
            expected_exists=True,
        ),
        RelationExistsTestCase(
            description="returns false for non-existing table",
            setup_sql=(),
            database=None,
            schema=None,
            name="missing_table",
            expected_exists=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relation_state_when_checking_exists_then_returns_expected(
    test_case: RelationExistsTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    result: bool = adapter.relation_exists(
        connection=connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert result == test_case.expected_exists


@pytest.mark.parametrize(
    "test_case",
    [
        ListRelationsTestCase(
            description="lists only relations in the requested schemas",
            setup_sql=(
                "CREATE TABLE orders (id INTEGER)",
                "CREATE VIEW orders_view AS SELECT id FROM orders",
                "CREATE SCHEMA other_schema",
                "CREATE TABLE other_schema.hidden (id INTEGER)",
            ),
            database=None,
            schemas=("main",),
            names=None,
            expected_names=("orders", "orders_view"),
        ),
        ListRelationsTestCase(
            description="lists relations across multiple requested schemas",
            setup_sql=(
                "CREATE TABLE orders (id INTEGER)",
                "CREATE SCHEMA staging",
                "CREATE TABLE staging.raw_orders (id INTEGER)",
                "CREATE SCHEMA excluded",
                "CREATE TABLE excluded.hidden (id INTEGER)",
            ),
            database=None,
            schemas=("main", "staging"),
            names=None,
            expected_names=("orders", "raw_orders"),
        ),
        ListRelationsTestCase(
            description="lists only requested relation names across schemas",
            setup_sql=(
                "CREATE TABLE orders (id INTEGER)",
                "CREATE TABLE customers (id INTEGER)",
                "CREATE SCHEMA staging",
                "CREATE TABLE staging.raw_orders (id INTEGER)",
            ),
            database=None,
            schemas=("main", "staging"),
            names=("orders", "raw_orders"),
            expected_names=("orders", "raw_orders"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_with_relations_when_listing_then_returns_expected_names(
    test_case: ListRelationsTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    relations: tuple[Any, ...] = adapter.list_relations(
        connection=connection,
        database=test_case.database,
        schemas=test_case.schemas,
        names=test_case.names,
    )
    names: tuple[str, ...] = tuple(r.name for r in relations)

    assert names == test_case.expected_names


@pytest.mark.parametrize(
    "test_case",
    [
        GetColumnsTestCase(
            description="returns columns with types in ordinal order",
            setup_sql=("CREATE TABLE typed_table (id INTEGER, name VARCHAR, active BOOLEAN)",),
            database=None,
            schema=None,
            name="typed_table",
            expected_columns=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="name", type="VARCHAR"),
                ColumnInfo(name="active", type="BOOLEAN"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_when_getting_columns_then_returns_typed_column_info(
    test_case: GetColumnsTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection=connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert columns == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        GetAllColumnsTestCase(
            description="returns all columns grouped by table name",
            setup_sql=(
                "CREATE TABLE t1 (a INTEGER, b VARCHAR)",
                "CREATE TABLE t2 (x BOOLEAN)",
            ),
            database=None,
            schemas=("main",),
            names=None,
            expected_columns_by_table={
                "t1": (ColumnInfo(name="a", type="INTEGER"), ColumnInfo(name="b", type="VARCHAR")),
                "t2": (ColumnInfo(name="x", type="BOOLEAN"),),
            },
        ),
        GetAllColumnsTestCase(
            description="returns only columns for requested table names",
            setup_sql=(
                "CREATE TABLE t1 (a INTEGER, b VARCHAR)",
                "CREATE TABLE t2 (x BOOLEAN)",
            ),
            database=None,
            schemas=("main",),
            names=("t1",),
            expected_columns_by_table={
                "t1": (ColumnInfo(name="a", type="INTEGER"), ColumnInfo(name="b", type="VARCHAR")),
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_with_tables_when_getting_all_columns_then_returns_grouped(
    test_case: GetAllColumnsTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    all_columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
        connection=connection,
        database=test_case.database,
        schemas=test_case.schemas,
        names=test_case.names,
    )

    assert frozenset(all_columns.keys()) == frozenset(test_case.expected_columns_by_table.keys())
    table_name: str
    expected_cols: tuple[ColumnInfo, ...]
    for table_name, expected_cols in test_case.expected_columns_by_table.items():
        assert all_columns[table_name] == expected_cols


@pytest.mark.parametrize(
    "test_case",
    [
        MaterializeTestCase(
            description="creates writable table from select",
            setup_sql=(),
            expected_row_count=4,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_when_creating_table_as_then_table_is_writable(
    test_case: MaterializeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    adapter.create_table_as(
        connection=connection,
        destination="result",
        sql="SELECT * FROM (VALUES (1), (2), (3)) AS t(id)",
        statement_recorder=StatementRecorder(),
    )
    connection.execute("INSERT INTO result VALUES (4)")
    count: int = adapter.count_rows(connection=connection, relation="result")

    assert count == test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [
        RecorderWriteTestCase(
            description="create_table_as records rendered statement before execution",
            setup_sql=(),
            operation="create_table_as",
            target="recorded_table",
            sql="SELECT * FROM (VALUES (1), (2)) AS t(id)",
            expected_recorded_statements=(
                "CREATE OR REPLACE TABLE recorded_table AS SELECT * FROM "
                "(VALUES (1), (2)) AS t(id)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_statement_recorder_when_creating_table_then_records_expected_sql(
    test_case: RecorderWriteTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    recorder: StatementRecorder = StatementRecorder()

    adapter.create_table_as(
        connection=connection,
        destination=test_case.target,
        sql=test_case.sql,
        statement_recorder=recorder,
    )

    actual_statements: tuple[str, ...] = tuple(event.content for event in recorder.snapshot())
    assert actual_statements == test_case.expected_recorded_statements


@pytest.mark.parametrize(
    "test_case",
    [
        RecorderWriteTestCase(
            description="delete_insert records delete and insert statements before execution",
            setup_sql=(
                "CREATE TABLE recorded_delete_insert (id INTEGER, val VARCHAR)",
                "INSERT INTO recorded_delete_insert VALUES (1, 'old'), (2, 'keep')",
            ),
            operation="delete_insert",
            target="recorded_delete_insert",
            sql="SELECT * FROM (VALUES (1, 'new')) AS t(id, val)",
            expected_recorded_statements=(
                "DELETE FROM recorded_delete_insert WHERE EXISTS "
                "(SELECT 1 FROM (SELECT * FROM (VALUES (1, 'new')) AS t(id, val)) "
                'AS __source WHERE recorded_delete_insert."id" = __source."id")',
                "INSERT INTO recorded_delete_insert SELECT * FROM "
                "(VALUES (1, 'new')) AS t(id, val)",
            ),
            unique_key="id",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_statement_recorder_when_delete_inserting_then_records_expected_sql(
    test_case: RecorderWriteTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    recorder: StatementRecorder = StatementRecorder()

    adapter.delete_insert(
        connection=connection,
        destination=test_case.target,
        sql=test_case.sql,
        unique_key=test_case.unique_key or "id",
        statement_recorder=recorder,
    )

    actual_statements: tuple[str, ...] = tuple(event.content for event in recorder.snapshot())
    assert actual_statements == test_case.expected_recorded_statements


@pytest.mark.parametrize(
    "test_case",
    [
        MaterializeTestCase(
            description="creates view from select",
            setup_sql=(
                "CREATE TABLE source (id INTEGER)",
                "INSERT INTO source VALUES (1), (2)",
            ),
            expected_row_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_table_when_creating_view_then_view_reflects_source(
    test_case: MaterializeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.create_view_as(
        connection=connection,
        destination="result_view",
        sql="SELECT id FROM source",
        statement_recorder=StatementRecorder(),
    )
    count: int = adapter.count_rows(connection=connection, relation="result_view")

    assert count == test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [
        DropTestCase(
            description="drops existing table",
            setup_sql=("CREATE TABLE to_drop (id INTEGER)",),
            target="to_drop",
            expected_exists=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_table_when_dropping_then_table_no_longer_exists(
    test_case: DropTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.drop(
        connection=connection, destination=test_case.target, statement_recorder=StatementRecorder()
    )

    result: bool = adapter.relation_exists(
        connection=connection, database=None, schema=None, name=test_case.target
    )
    assert result == test_case.expected_exists


@pytest.mark.parametrize(
    "test_case",
    [
        RenameTestCase(
            description="renames table",
            setup_sql=(
                "CREATE TABLE original (id INTEGER)",
                "INSERT INTO original VALUES (1)",
            ),
            source="original",
            target="renamed",
            expected_source_exists=False,
            expected_target_exists=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_table_when_renaming_then_new_name_exists(
    test_case: RenameTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.rename(
        connection=connection,
        origin=test_case.source,
        destination=test_case.target,
        statement_recorder=StatementRecorder(),
    )

    source_exists: bool = adapter.relation_exists(
        connection=connection, database=None, schema=None, name=test_case.source
    )
    target_exists: bool = adapter.relation_exists(
        connection=connection, database=None, schema=None, name=test_case.target
    )
    assert source_exists == test_case.expected_source_exists
    assert target_exists == test_case.expected_target_exists


@pytest.mark.parametrize(
    "test_case",
    [
        RenameTestCase(
            description="move-or-copy uses native rename within one schema",
            setup_sql=(
                "CREATE SCHEMA move_native",
                "CREATE TABLE move_native.original (id INTEGER)",
                "INSERT INTO move_native.original VALUES (1)",
            ),
            source="move_native.original",
            target="move_native.renamed",
            expected_source_exists=False,
            expected_target_exists=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_same_schema_table_when_moving_without_copy_then_native_rename_is_used(
    test_case: RenameTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    adapter.move_or_copy_relation(
        connection=connection,
        origin=test_case.source,
        destination=test_case.target,
        remove_origin=True,
        allow_copy_fallback=False,
        statement_recorder=StatementRecorder(),
    )

    source_exists: bool = adapter.relation_exists(
        connection=connection, database=None, schema="move_native", name="original"
    )
    target_exists: bool = adapter.relation_exists(
        connection=connection, database=None, schema="move_native", name="renamed"
    )
    assert source_exists == test_case.expected_source_exists
    assert target_exists == test_case.expected_target_exists


@pytest.mark.parametrize(
    "test_case",
    [
        SwapTestCase(
            description="swaps two tables",
            setup_sql=(
                "CREATE TABLE left_t (val VARCHAR)",
                "INSERT INTO left_t VALUES ('left')",
                "CREATE TABLE right_t (val VARCHAR)",
                "INSERT INTO right_t VALUES ('right')",
            ),
            expected_left_value="right",
            expected_right_value="left",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_tables_when_swapping_then_contents_are_exchanged(
    test_case: SwapTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.swap(
        connection=connection,
        left="left_t",
        right="right_t",
        statement_recorder=StatementRecorder(),
    )
    left_val: Any = connection.execute("SELECT val FROM left_t").fetchone()
    right_val: Any = connection.execute("SELECT val FROM right_t").fetchone()

    assert left_val[0] == test_case.expected_left_value
    assert right_val[0] == test_case.expected_right_value


@pytest.mark.parametrize(
    "test_case",
    [
        MaterializeTestCase(
            description="clones table contents",
            setup_sql=(
                "CREATE TABLE source_t (id INTEGER)",
                "INSERT INTO source_t VALUES (1), (2), (3)",
            ),
            expected_row_count=3,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_table_when_cloning_then_target_has_same_rows(
    test_case: MaterializeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.clone(
        connection=connection,
        origin="source_t",
        destination="cloned_t",
        statement_recorder=StatementRecorder(),
    )
    count: int = adapter.count_rows(connection=connection, relation="cloned_t")

    assert count == test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [
        MaterializeTestCase(
            description="appends rows to existing table",
            setup_sql=(
                "CREATE TABLE append_t (id INTEGER)",
                "INSERT INTO append_t VALUES (1)",
            ),
            expected_row_count=3,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_table_when_appending_then_row_count_increases(
    test_case: MaterializeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.append(
        connection=connection,
        destination="append_t",
        sql="SELECT * FROM (VALUES (2), (3)) AS t(id)",
        statement_recorder=StatementRecorder(),
    )
    count: int = adapter.count_rows(connection=connection, relation="append_t")

    assert count == test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [
        DeleteInsertTestCase(
            description="delete inserts by unique key",
            setup_sql=(
                "CREATE TABLE di_target (id INTEGER, val VARCHAR)",
                "INSERT INTO di_target VALUES (1, 'old'), (2, 'keep')",
            ),
            sql="SELECT * FROM (VALUES (1, 'new')) AS t(id, val)",
            unique_key="id",
            expected_row_count=2,
            expected_updated_value="new",
        ),
        DeleteInsertTestCase(
            description="removes duplicate target rows when source is deduplicated",
            setup_sql=(
                "CREATE TABLE di_target (id INTEGER, val VARCHAR)",
                "INSERT INTO di_target VALUES (1, 'dup_a'), (1, 'dup_b'), (2, 'keep')",
            ),
            sql="SELECT * FROM (VALUES (1, 'fixed')) AS t(id, val)",
            unique_key="id",
            expected_row_count=2,
            expected_updated_value="fixed",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_when_delete_inserting_then_matching_rows_replaced(
    test_case: DeleteInsertTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.delete_insert(
        connection=connection,
        destination="di_target",
        sql=test_case.sql,
        unique_key=test_case.unique_key,
        statement_recorder=StatementRecorder(),
    )
    count: int = adapter.count_rows(connection=connection, relation="di_target")
    updated_val: Any = connection.execute("SELECT val FROM di_target WHERE id = 1").fetchone()

    assert count == test_case.expected_row_count
    assert updated_val[0] == test_case.expected_updated_value


@pytest.mark.parametrize(
    "test_case",
    [
        MergeTestCase(
            description="inserts new rows and updates existing via merge",
            setup_sql=(
                "CREATE TABLE merge_target (id INTEGER, name VARCHAR)",
                "INSERT INTO merge_target VALUES (1, 'alice'), (2, 'bob')",
            ),
            source_sql="SELECT * FROM (VALUES (2, 'robert'), (3, 'charlie')) AS t(id, name)",
            unique_key="id",
            expected_row_count=3,
            expected_values=((1, "alice"), (2, "robert"), (3, "charlie")),
        ),
        MergeTestCase(
            description="preserves duplicate target rows that upsert cannot remove",
            setup_sql=(
                "CREATE TABLE merge_target (id INTEGER, name VARCHAR)",
                "INSERT INTO merge_target VALUES (1, 'dup_a'), (1, 'dup_b'), (2, 'bob')",
            ),
            source_sql="SELECT * FROM (VALUES (1, 'fixed')) AS t(id, name)",
            unique_key="id",
            expected_row_count=3,
            expected_values=((1, "fixed"), (1, "fixed"), (2, "bob")),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_and_source_when_merging_then_upserts_correctly(
    test_case: MergeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter.merge(
        connection=connection,
        destination="merge_target",
        sql=test_case.source_sql,
        unique_key=test_case.unique_key,
        statement_recorder=StatementRecorder(),
    )
    count: int = adapter.count_rows(connection=connection, relation="merge_target")
    rows: list[tuple[Any, ...]] = connection.execute(
        "SELECT id, name FROM merge_target ORDER BY id, name"
    ).fetchall()

    assert count == test_case.expected_row_count
    assert tuple(tuple(r) for r in rows) == test_case.expected_values


@pytest.mark.parametrize(
    "test_case",
    [
        LoadSeedTestCase(
            description="loads csv with explicit column types",
            csv_content="id,name\n1,alice\n2,bob\n",
            columns=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="name", type="VARCHAR"),
            ),
            infer_types=False,
            expected_row_count=2,
            expected_first_row=(1, "alice"),
        ),
        LoadSeedTestCase(
            description="loads csv with inferred types",
            csv_content="id,name\n1,alice\n2,bob\n",
            columns=(),
            infer_types=True,
            expected_row_count=2,
            expected_first_row=(1, "alice"),
        ),
        LoadSeedTestCase(
            description="loads csv with custom delimiter",
            csv_content="id|name\n1|alice\n2|bob\n",
            columns=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="name", type="VARCHAR"),
            ),
            infer_types=False,
            expected_row_count=2,
            expected_first_row=(1, "alice"),
            csv_settings=SeedCsvSettings(delimiter="|"),
            expected_recorded_fragment="delim='|'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_csv_file_when_loading_seed_twice_then_table_is_replaced(
    test_case: LoadSeedTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    tmp_path: Path,
) -> None:
    csv_path: Path = tmp_path / "seed.csv"
    csv_path.write_text(test_case.csv_content, encoding="utf-8")
    first_recorder: StatementRecorder = StatementRecorder()
    adapter.load_seed(
        connection=connection,
        destination="seed_table",
        file_path=csv_path,
        columns=test_case.columns,
        csv_settings=test_case.csv_settings,
        infer_types=test_case.infer_types,
        statement_recorder=first_recorder,
    )
    adapter.load_seed(
        connection=connection,
        destination="seed_table",
        file_path=csv_path,
        columns=test_case.columns,
        csv_settings=test_case.csv_settings,
        replace=True,
        infer_types=test_case.infer_types,
        statement_recorder=StatementRecorder(),
    )
    count: int = adapter.count_rows(connection=connection, relation="seed_table")
    first_row: tuple[Any, ...] = connection.execute(
        "SELECT * FROM seed_table ORDER BY id LIMIT 1"
    ).fetchone()

    assert count == test_case.expected_row_count
    assert tuple(first_row) == test_case.expected_first_row
    assert test_case.expected_recorded_fragment in "\n".join(
        event.content for event in first_recorder.snapshot()
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DiffSchemaTestCase(
            description="detects added removed and type changed columns",
            left_sql="CREATE TABLE left_t (id INTEGER, name VARCHAR, old_col BOOLEAN)",
            right_sql="CREATE TABLE right_t (id BIGINT, name VARCHAR, new_col DATE)",
            expected_result=SchemaDiffResult(
                added_columns=(ColumnInfo(name="new_col", type="DATE"),),
                removed_columns=(ColumnInfo(name="old_col", type="BOOLEAN"),),
                type_changed_columns=(
                    (
                        ColumnInfo(name="id", type="INTEGER"),
                        ColumnInfo(name="id", type="BIGINT"),
                    ),
                ),
            ),
        ),
        DiffSchemaTestCase(
            description="returns empty result for identical schemas",
            left_sql="CREATE TABLE left_t (id INTEGER, name VARCHAR)",
            right_sql="CREATE TABLE right_t (id INTEGER, name VARCHAR)",
            expected_result=SchemaDiffResult(),
        ),
        DiffSchemaTestCase(
            description="ignores equivalent scalar aliases and detects numeric scale changes",
            left_sql=(
                "CREATE TABLE left_t ("
                "id INTEGER, flag BOOLEAN, amount DECIMAL(10,2), widened DECIMAL(10,2))"
            ),
            right_sql=(
                "CREATE TABLE right_t (id INT, flag BOOL, amount NUMERIC(10,2), widened NUMERIC(10,3))"
            ),
            expected_result=SchemaDiffResult(
                type_changed_columns=(
                    (
                        ColumnInfo(name="widened", type="DECIMAL(10,2)"),
                        ColumnInfo(name="widened", type="DECIMAL(10,3)"),
                    ),
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_tables_when_diffing_schema_then_returns_expected_differences(
    test_case: DiffSchemaTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute(test_case.left_sql)
    connection.execute(test_case.right_sql)

    result: SchemaDiffResult = adapter.diff_schema(
        connection=connection, left="left_t", right="right_t"
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        DiffRowsTestCase(
            description="detects matching mismatched and missing rows",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM "
                "(VALUES (1, 'a'), (2, 'b'), (3, 'c')) AS t(id, val)"
            ),
            right_sql=(
                "CREATE TABLE right_t AS SELECT * FROM "
                "(VALUES (1, 'a'), (2, 'x'), (4, 'd')) AS t(id, val)"
            ),
            unique_key="id",
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
        DiffRowsTestCase(
            description="excludes columns from comparison",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM (VALUES (1, 'a', 'ignore1')) AS t(id, val, extra)"
            ),
            right_sql=(
                "CREATE TABLE right_t AS SELECT * FROM "
                "(VALUES (1, 'a', 'ignore2')) AS t(id, val, extra)"
            ),
            unique_key="id",
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
        DiffRowsTestCase(
            description="allows absolute tolerance for numeric columns",
            left_sql="CREATE TABLE left_t AS SELECT * FROM (VALUES (1, 100.00)) AS t(id, amount)",
            right_sql="CREATE TABLE right_t AS SELECT * FROM (VALUES (1, 100.005)) AS t(id, amount)",
            unique_key="id",
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
        DiffRowsTestCase(
            description="allows relative tolerance for float columns",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM "
                "(VALUES (1, CAST(1000000.0 AS DOUBLE))) AS t(id, metric)"
            ),
            right_sql=(
                "CREATE TABLE right_t AS SELECT * FROM "
                "(VALUES (1, CAST(1000050.0 AS DOUBLE))) AS t(id, metric)"
            ),
            unique_key="id",
            tolerances=RowDiffTolerances(
                by_type={"float": RowDiffTolerance(relative=Decimal("0.0001"))},
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
        DiffRowsTestCase(
            description="reports numeric difference outside tolerance",
            left_sql="CREATE TABLE left_t AS SELECT * FROM (VALUES (1, 100.00)) AS t(id, amount)",
            right_sql="CREATE TABLE right_t AS SELECT * FROM (VALUES (1, 100.02)) AS t(id, amount)",
            unique_key="id",
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
        DiffRowsTestCase(
            description="uses larger of absolute and relative tolerance",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM "
                "(VALUES (1, CAST(1000000.0 AS DOUBLE))) AS t(id, metric)"
            ),
            right_sql=(
                "CREATE TABLE right_t AS SELECT * FROM "
                "(VALUES (1, CAST(1000050.0 AS DOUBLE))) AS t(id, metric)"
            ),
            unique_key="id",
            tolerances=RowDiffTolerances(
                by_column={
                    "metric": RowDiffTolerance(
                        absolute=Decimal("0.01"),
                        relative=Decimal("0.0001"),
                    )
                },
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
                        tolerance=RowDiffTolerance(
                            absolute=Decimal("0.01"),
                            relative=Decimal("0.0001"),
                        ),
                    ),
                ),
            ),
        ),
        DiffRowsTestCase(
            description="keeps null versus value different with tolerance",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM "
                "(VALUES (1, CAST(NULL AS DOUBLE))) AS t(id, amount)"
            ),
            right_sql="CREATE TABLE right_t AS SELECT * FROM (VALUES (1, 100.00)) AS t(id, amount)",
            unique_key="id",
            tolerances=RowDiffTolerances(
                by_column={"amount": RowDiffTolerance(absolute=Decimal("1000"))},
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
                        tolerance=RowDiffTolerance(absolute=Decimal("1000")),
                    ),
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_tables_when_diffing_rows_then_returns_expected_counts(
    test_case: DiffRowsTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute(test_case.left_sql)
    connection.execute(test_case.right_sql)

    result: RowDiffResult = adapter.diff_rows(
        connection=connection,
        left="left_t",
        right="right_t",
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
    [
        DiffRowsErrorTestCase(
            description="rejects tolerance for non numeric column",
            left_sql="CREATE TABLE left_t AS SELECT * FROM (VALUES (1, 'a')) AS t(id, status)",
            right_sql="CREATE TABLE right_t AS SELECT * FROM (VALUES (1, 'b')) AS t(id, status)",
            unique_key="id",
            tolerances=RowDiffTolerances(
                by_column={"status": RowDiffTolerance(absolute=Decimal("1"))},
            ),
            expected_error_fragment="row diff tolerance for non-numeric column 'status' is invalid",
        ),
        DiffRowsErrorTestCase(
            description="rejects empty tolerance",
            left_sql="CREATE TABLE left_t AS SELECT * FROM (VALUES (1, 100.0)) AS t(id, amount)",
            right_sql="CREATE TABLE right_t AS SELECT * FROM (VALUES (1, 100.0)) AS t(id, amount)",
            unique_key="id",
            tolerances=RowDiffTolerances(by_column={"amount": RowDiffTolerance()}),
            expected_error_fragment="must define absolute or relative",
        ),
        DiffRowsErrorTestCase(
            description="rejects null left unique key",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM "
                "(VALUES (CAST(NULL AS INTEGER), 'a')) AS t(id, status)"
            ),
            right_sql="CREATE TABLE right_t AS SELECT * FROM (VALUES (1, 'a')) AS t(id, status)",
            unique_key="id",
            expected_error_fragment="left relation contains null unique_key values",
        ),
        DiffRowsErrorTestCase(
            description="rejects duplicate right unique key",
            left_sql="CREATE TABLE left_t AS SELECT * FROM (VALUES (1, 'a')) AS t(id, status)",
            right_sql=(
                "CREATE TABLE right_t AS SELECT * FROM (VALUES (1, 'a'), (1, 'b')) AS t(id, status)"
            ),
            unique_key="id",
            expected_error_fragment="right relation contains duplicate unique_key values",
        ),
        DiffRowsErrorTestCase(
            description="rejects null composite unique key component",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM "
                "(VALUES (1, CAST(NULL AS INTEGER), 'a')) AS t(id, line_number, status)"
            ),
            right_sql=(
                "CREATE TABLE right_t AS SELECT * FROM "
                "(VALUES (1, 1, 'a')) AS t(id, line_number, status)"
            ),
            unique_key=("id", "line_number"),
            expected_error_fragment="left relation contains null unique_key values",
        ),
        DiffRowsErrorTestCase(
            description="rejects duplicate composite unique key",
            left_sql=(
                "CREATE TABLE left_t AS SELECT * FROM "
                "(VALUES (1, 1, 'a'), (1, 1, 'b')) AS t(id, line_number, status)"
            ),
            right_sql=(
                "CREATE TABLE right_t AS SELECT * FROM "
                "(VALUES (1, 1, 'a')) AS t(id, line_number, status)"
            ),
            unique_key=("id", "line_number"),
            expected_error_fragment="left relation contains duplicate unique_key values",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_tolerance_when_diffing_rows_then_raises_clear_error(
    test_case: DiffRowsErrorTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute(test_case.left_sql)
    connection.execute(test_case.right_sql)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        adapter.diff_rows(
            connection=connection,
            left="left_t",
            right="right_t",
            unique_key=test_case.unique_key,
            tolerances=test_case.tolerances,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        CountRowsTestCase(
            description="counts all rows without cursor filter",
            setup_sql=(
                "CREATE TABLE count_t (id INTEGER)",
                "INSERT INTO count_t VALUES (1), (2), (3)",
            ),
            relation="count_t",
            expected_count=3,
        ),
        CountRowsTestCase(
            description="counts rows bounded by integer cursor",
            setup_sql=(
                "CREATE TABLE count_bounded (id INTEGER)",
                "INSERT INTO count_bounded VALUES (1), (2), (3), (4), (5)",
            ),
            relation="count_bounded",
            cursor_column="id",
            start_cursor=CursorValue(kind=CursorKind.INTEGER, value=2),
            end_cursor=CursorValue(kind=CursorKind.INTEGER, value=4),
            expected_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_when_counting_rows_then_returns_expected_count(
    test_case: CountRowsTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    count: int = adapter.count_rows(
        connection=connection,
        relation=test_case.relation,
        cursor_column=test_case.cursor_column,
        start_cursor=test_case.start_cursor,
        end_cursor=test_case.end_cursor,
    )

    assert count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [
        TransactionalAtomicityTestCase(
            description="delete_insert rolls back delete when insert fails",
            setup_sql=(
                "CREATE TABLE atomic_di (id INTEGER NOT NULL, val VARCHAR NOT NULL)",
                "INSERT INTO atomic_di VALUES (1, 'keep'), (2, 'keep')",
            ),
            target="atomic_di",
            source_sql="SELECT * FROM (VALUES (1, NULL)) AS t(id, val)",
            unique_key="id",
            verify_sql="SELECT id, val FROM atomic_di ORDER BY id",
            expected_rows_after_failure=((1, "keep"), (2, "keep")),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_insert_when_delete_inserting_then_original_rows_preserved(
    test_case: TransactionalAtomicityTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    with pytest.raises(duckdb.ConstraintException):
        adapter.delete_insert(
            connection=connection,
            destination=test_case.target,
            sql=test_case.source_sql,
            unique_key=test_case.unique_key,
            statement_recorder=StatementRecorder(),
        )

    actual: tuple[tuple[object, ...], ...] = tuple(
        connection.execute(test_case.verify_sql).fetchall()
    )
    assert actual == test_case.expected_rows_after_failure


@pytest.mark.parametrize(
    "test_case",
    [
        TransactionalAtomicityTestCase(
            description="delete_insert_cursor rolls back on NOT NULL failure",
            setup_sql=(
                "CREATE TABLE atomic_dic "
                "(id INTEGER NOT NULL, val VARCHAR NOT NULL, cursor_ts VARCHAR NOT NULL)",
                "INSERT INTO atomic_dic VALUES "
                "(1, 'keep', '2024-01-01'), (2, 'keep', '2024-01-02')",
            ),
            target="atomic_dic",
            source_sql="SELECT * FROM (VALUES (1, NULL, '2024-01-01')) AS t(id, val, cursor_ts)",
            unique_key="id",
            verify_sql="SELECT id, val FROM atomic_dic ORDER BY id",
            expected_rows_after_failure=((1, "keep"), (2, "keep")),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_insert_when_delete_insert_cursor_then_original_rows_preserved(
    test_case: TransactionalAtomicityTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    with pytest.raises(duckdb.ConstraintException):
        adapter.delete_insert_cursor(
            connection=connection,
            destination=test_case.target,
            sql=test_case.source_sql,
            cursor_column="cursor_ts",
            cursor_start="2024-01-01",
            cursor_end="2024-01-03",
            statement_recorder=StatementRecorder(),
        )

    actual: tuple[tuple[object, ...], ...] = tuple(
        connection.execute(test_case.verify_sql).fetchall()
    )
    assert actual == test_case.expected_rows_after_failure


@pytest.mark.parametrize(
    "test_case",
    [
        TransactionalAtomicityTestCase(
            description="swap rolls back partial renames on failure",
            setup_sql=(
                "CREATE TABLE swap_left (val VARCHAR)",
                "INSERT INTO swap_left VALUES ('left')",
            ),
            target="swap_left",
            source_sql="",
            unique_key="",
            verify_sql="SELECT val FROM swap_left",
            expected_rows_after_failure=(("left",),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_right_table_when_swapping_then_left_table_preserved(
    test_case: TransactionalAtomicityTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    with pytest.raises(duckdb.CatalogException):
        adapter.swap(
            connection=connection,
            left="swap_left",
            right="swap_nonexistent",
            statement_recorder=StatementRecorder(),
        )

    actual: tuple[tuple[object, ...], ...] = tuple(
        connection.execute(test_case.verify_sql).fetchall()
    )
    assert actual == test_case.expected_rows_after_failure
