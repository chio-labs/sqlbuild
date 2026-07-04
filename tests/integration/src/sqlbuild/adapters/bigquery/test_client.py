from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    ExpressionInferenceProfile,
    QueryResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    SchemaDiffResult,
    StatementRecorder,
    TableFreshnessMetadata,
    TableFreshnessRequest,
)
from sqlbuild.adapter.shared.types import FunctionNullabilityRule
from sqlbuild.adapters.bigquery.client import BigQueryAdapter
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.executor.run.helpers.reuse.core import create_relation_from_reuse_origin
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.main.state_record import source_freshness_record_from_observation
from sqlbuild.virtual.freshness.models import SourceFreshnessObservation
from tests.integration.src.sqlbuild.adapters.bigquery._test_types import (
    BigQueryBuildFlowTestCase,
    BigQueryDeleteInsertCursorTestCase,
    BigQueryExpressionNullabilityRuleTestCase,
    BigQueryFingerprintTestCase,
    BigQueryMergeTestCase,
    BigQueryQueryTestCase,
    BigQueryRelationReuseCopyTestCase,
    BigQueryRowDiffSampleTestCase,
    BigQueryRowDiffTestCase,
    BigQuerySchemaDiffTestCase,
    BigQuerySchemaIntrospectionTestCase,
    BigQueryTableFreshnessMetadataTestCase,
)
from tests.integration.src.sqlbuild.adapters.bigquery.helpers import (
    build_statement_recorder,
    execute_statements,
    fetch_rows,
    qualified_name,
    wait_for_bigquery_freshness_after,
    write_seed_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryExpressionNullabilityRuleTestCase(
            description="LOWER preserves non-null literal",
            function_name="LOWER",
            sql_expression="LOWER('READY')",
            rule_args=(InferredNullability.NON_NULL,),
            expected_nullability=InferredNullability.NON_NULL,
            expected_is_null=False,
        ),
        BigQueryExpressionNullabilityRuleTestCase(
            description="LOWER preserves nullable input",
            function_name="LOWER",
            sql_expression="LOWER(CAST(NULL AS STRING))",
            rule_args=(InferredNullability.NULLABLE,),
            expected_nullability=InferredNullability.NULLABLE,
            expected_is_null=True,
        ),
        BigQueryExpressionNullabilityRuleTestCase(
            description="IF with non-null result branches is non-null",
            function_name="IF",
            sql_expression="IF(TRUE, 'yes', 'no')",
            rule_args=(
                InferredNullability.UNKNOWN,
                InferredNullability.NON_NULL,
                InferredNullability.NON_NULL,
            ),
            expected_nullability=InferredNullability.NON_NULL,
            expected_is_null=False,
        ),
        BigQueryExpressionNullabilityRuleTestCase(
            description="IF with nullable result branch can be null",
            function_name="IF",
            sql_expression="IF(TRUE, CAST(NULL AS STRING), 'no')",
            rule_args=(
                InferredNullability.UNKNOWN,
                InferredNullability.NULLABLE,
                InferredNullability.NON_NULL,
            ),
            expected_nullability=InferredNullability.NULLABLE,
            expected_is_null=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expression_rule_when_querying_then_bigquery_matches_nullability_expectation(
    test_case: BigQueryExpressionNullabilityRuleTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
) -> None:
    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()
    rule: FunctionNullabilityRule | None = profile.function_nullability_rule(
        test_case.function_name
    )
    assert rule is not None

    result: QueryResult = adapter.query(
        connection,
        f"SELECT {test_case.sql_expression} IS NULL AS is_null",
        limit=None,
    )

    assert rule(test_case.rule_args) == test_case.expected_nullability
    assert result.rows == ((test_case.expected_is_null,),)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryQueryTestCase(
            description="returns rows and truncation for limited query",
            sql=(
                "SELECT * FROM ("
                "SELECT 1 AS id, 'alice' AS name UNION ALL "
                "SELECT 2 AS id, 'bob' AS name"
                ") ORDER BY id"
            ),
            limit=1,
            expected_result=QueryResult(
                columns=("id", "name"),
                rows=((1, "alice"),),
                truncated=True,
            ),
        ),
        BigQueryQueryTestCase(
            description="returns all rows when limit is none",
            sql=(
                "SELECT * FROM ("
                "SELECT 1 AS id, 'alice' AS name UNION ALL "
                "SELECT 2 AS id, 'bob' AS name"
                ") ORDER BY id"
            ),
            limit=None,
            expected_result=QueryResult(
                columns=("id", "name"),
                rows=((1, "alice"), (2, "bob")),
                truncated=False,
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_when_querying_then_returns_expected_result(
    test_case: BigQueryQueryTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    ddl_target: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="__sqb_query_temp",
    )

    result: QueryResult = adapter.query(connection, test_case.sql, limit=test_case.limit)
    ddl_result: QueryResult = adapter.query(
        connection,
        f"CREATE OR REPLACE TABLE {ddl_target} (id INT64)",
        limit=20,
    )

    assert result == test_case.expected_result
    assert ddl_result == QueryResult()


@pytest.mark.parametrize(
    "test_case",
    [
        BigQuerySchemaIntrospectionTestCase(
            description="discovers created table and view metadata",
            setup_sql=(
                "CREATE OR REPLACE TABLE orders (id INT64, amount NUMERIC)",
                "CREATE OR REPLACE VIEW orders_view AS SELECT id, amount FROM orders",
            ),
            expected_relation_exists=True,
            expected_schema_exists=True,
            expected_relation_names=("orders", "orders_view"),
            expected_columns=(
                ColumnInfo(name="id", type="INT64"),
                ColumnInfo(name="amount", type="NUMERIC"),
            ),
            expected_all_columns={
                "orders": (
                    ColumnInfo(name="id", type="INT64"),
                    ColumnInfo(name="amount", type="NUMERIC"),
                )
            },
            expected_query_column_names=("order_id", "status"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relations_when_introspecting_then_returns_expected_metadata(
    test_case: BigQuerySchemaIntrospectionTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    orders_relation: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="orders",
    )
    orders_view_relation: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="orders_view",
    )
    rewritten_statements: tuple[str, ...] = tuple(
        statement.replace("TABLE orders ", f"TABLE {orders_relation} ", 1)
        .replace("VIEW orders_view ", f"VIEW {orders_view_relation} ", 1)
        .replace("FROM orders", f"FROM {orders_relation}", 1)
        for statement in test_case.setup_sql
    )
    execute_statements(adapter=adapter, connection=connection, statements=rewritten_statements)

    relation_exists: bool = adapter.relation_exists(
        connection,
        database=bigquery_project,
        schema=bigquery_dataset,
        name="orders",
    )
    schema_exists: bool = adapter.schema_exists(
        connection,
        database=bigquery_project,
        schema=bigquery_dataset,
    )
    relation_names: tuple[str, ...] = tuple(
        relation.name
        for relation in adapter.list_relations(
            connection,
            database=bigquery_project,
            schemas=(bigquery_dataset,),
        )
    )
    columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection,
        database=bigquery_project,
        schema=bigquery_dataset,
        name="orders",
    )
    all_columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
        connection,
        database=bigquery_project,
        schemas=(bigquery_dataset,),
        names=("orders",),
    )
    query_column_names: tuple[str, ...] = adapter.query_column_names(
        connection,
        "SELECT * FROM (SELECT 1 AS order_id, 'ok' AS status) AS named_rows",
    )
    described_columns: tuple[ColumnInfo, ...] = adapter.describe_relation(
        connection, orders_relation
    )

    assert relation_exists == test_case.expected_relation_exists
    assert schema_exists == test_case.expected_schema_exists
    assert tuple(sorted(relation_names)) == tuple(sorted(test_case.expected_relation_names))
    assert columns == test_case.expected_columns
    assert all_columns == test_case.expected_all_columns
    assert query_column_names == test_case.expected_query_column_names
    assert described_columns == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryTableFreshnessMetadataTestCase(
            description="table freshness metadata advances after table DML",
            expected_value_kind="timestamp",
            expected_supports_metadata=True,
            expected_data_version_type=datetime,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_dml_when_getting_freshness_metadata_then_modified_time_advances(
    test_case: BigQueryTableFreshnessMetadataTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    table_name: str = "freshness_orders"
    table_target: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name=table_name,
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            f"CREATE OR REPLACE TABLE {table_target} (id INT64)",
            f"INSERT INTO {table_target} VALUES (1)",
        ),
    )
    initial_metadata: TableFreshnessMetadata = adapter.get_table_freshness_metadata(
        connection,
        database=bigquery_project,
        schema=bigquery_dataset,
        name=table_name,
    )

    adapter.execute(connection, f"INSERT INTO {table_target} VALUES (2)")
    initial_data_version: object = initial_metadata.data_version
    assert isinstance(initial_data_version, test_case.expected_data_version_type)
    changed_metadata: TableFreshnessMetadata = wait_for_bigquery_freshness_after(
        adapter=adapter,
        connection=connection,
        database=bigquery_project,
        schema=bigquery_dataset,
        name=table_name,
        previous_data_version=initial_data_version,
    )
    batch_request: TableFreshnessRequest = TableFreshnessRequest(
        database=bigquery_project,
        schema=bigquery_dataset,
        name=table_name,
    )
    batch_metadata: TableFreshnessMetadata = adapter.get_tables_freshness_metadata(
        connection,
        requests=(batch_request,),
    )[batch_request]

    assert adapter.supports_table_freshness_metadata() is test_case.expected_supports_metadata
    assert initial_metadata.value_kind == test_case.expected_value_kind
    assert changed_metadata.value_kind == test_case.expected_value_kind
    assert batch_metadata.value_kind == test_case.expected_value_kind
    changed_data_version: object = changed_metadata.data_version
    assert isinstance(changed_data_version, test_case.expected_data_version_type)
    assert isinstance(batch_metadata.data_version, test_case.expected_data_version_type)
    assert changed_data_version > initial_data_version
    initial_hash: str = source_freshness_record_from_observation(
        SourceFreshnessObservation(
            source_name="raw_orders",
            strategy=SourceFreshnessStrategy.ADAPTER,
            data_version=initial_data_version,
            value_kind=SourceFreshnessValueKind(initial_metadata.value_kind),
            observed_at=datetime.now(tz=UTC),
        ),
        virtual_environment_name="dev",
    ).data_version_hash
    repeated_initial_hash: str = source_freshness_record_from_observation(
        SourceFreshnessObservation(
            source_name="raw_orders",
            strategy=SourceFreshnessStrategy.ADAPTER,
            data_version=initial_data_version,
            value_kind=SourceFreshnessValueKind(initial_metadata.value_kind),
            observed_at=datetime.now(tz=UTC),
        ),
        virtual_environment_name="dev",
    ).data_version_hash
    changed_hash: str = source_freshness_record_from_observation(
        SourceFreshnessObservation(
            source_name="raw_orders",
            strategy=SourceFreshnessStrategy.ADAPTER,
            data_version=changed_data_version,
            value_kind=SourceFreshnessValueKind(changed_metadata.value_kind),
            observed_at=datetime.now(tz=UTC),
        ),
        virtual_environment_name="dev",
    ).data_version_hash
    assert repeated_initial_hash == initial_hash
    assert changed_hash != initial_hash


@pytest.mark.parametrize(
    "test_case",
    [
        BigQuerySchemaDiffTestCase(
            description="detects added removed and changed column types",
            left_sql="CREATE OR REPLACE TABLE left_t (id INT64, status STRING, old_col BOOL)",
            right_sql="CREATE OR REPLACE TABLE right_t (id STRING, status STRING, new_col DATE)",
            expected_result=SchemaDiffResult(
                added_columns=(ColumnInfo(name="new_col", type="DATE"),),
                removed_columns=(ColumnInfo(name="old_col", type="BOOL"),),
                type_changed_columns=(
                    (
                        ColumnInfo(name="id", type="INT64"),
                        ColumnInfo(name="id", type="STRING"),
                    ),
                ),
            ),
        ),
        BigQuerySchemaDiffTestCase(
            description="ignores equivalent scalar aliases and detects numeric scale changes",
            left_sql=(
                "CREATE OR REPLACE TABLE left_t ("
                "id INT64, flag BOOL, amount NUMERIC(10,2), widened NUMERIC(10,2))"
            ),
            right_sql=(
                "CREATE OR REPLACE TABLE right_t ("
                "id INTEGER, flag BOOLEAN, amount DECIMAL(10,2), widened DECIMAL(10,3))"
            ),
            expected_result=SchemaDiffResult(
                type_changed_columns=(
                    (
                        ColumnInfo(name="widened", type="NUMERIC(10,2)"),
                        ColumnInfo(name="widened", type="NUMERIC(10,3)"),
                    ),
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relations_when_diffing_schema_then_returns_expected_result(
    test_case: BigQuerySchemaDiffTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    left_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="left_t",
    )
    right_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="right_t",
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    result: SchemaDiffResult = adapter.diff_schema(connection, left=left_name, right=right_name)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRowDiffTestCase(
            description="detects equal unequal and side-only rows",
            left_sql=(
                "CREATE OR REPLACE TABLE left_t AS "
                "SELECT 1 AS id, 'a' AS val UNION ALL "
                "SELECT 2 AS id, 'b' AS val UNION ALL "
                "SELECT 3 AS id, 'c' AS val"
            ),
            right_sql=(
                "CREATE OR REPLACE TABLE right_t AS "
                "SELECT 1 AS id, 'a' AS val UNION ALL "
                "SELECT 2 AS id, 'x' AS val UNION ALL "
                "SELECT 4 AS id, 'd' AS val"
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
            ),
        ),
        BigQueryRowDiffTestCase(
            description="counts equal rows for identical tables",
            left_sql="CREATE OR REPLACE TABLE left_t AS SELECT 1 AS id, 10 AS amount",
            right_sql="CREATE OR REPLACE TABLE right_t AS SELECT 1 AS id, 10 AS amount",
            unique_key="id",
            expected_result=RowDiffResult(
                left_count=1,
                right_count=1,
                joined_count=1,
                equal_count=1,
                unequal_count=0,
                left_only_count=0,
                right_only_count=0,
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relations_when_diffing_rows_then_returns_expected_result(
    test_case: BigQueryRowDiffTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    left_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="left_t",
    )
    right_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="right_t",
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    result: RowDiffResult = adapter.diff_rows(
        connection,
        left=left_name,
        right=right_name,
        unique_key=test_case.unique_key,
    )

    assert result.left_count == test_case.expected_result.left_count
    assert result.right_count == test_case.expected_result.right_count
    assert result.joined_count == test_case.expected_result.joined_count
    assert result.equal_count == test_case.expected_result.equal_count
    assert result.unequal_count == test_case.expected_result.unequal_count
    assert result.left_only_count == test_case.expected_result.left_only_count
    assert result.right_only_count == test_case.expected_result.right_only_count


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRowDiffSampleTestCase(
            description="returns unequal row samples for changed values",
            left_sql=(
                "CREATE OR REPLACE TABLE left_t AS "
                "SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val"
            ),
            right_sql=(
                "CREATE OR REPLACE TABLE right_t AS "
                "SELECT 1 AS id, 'x' AS val UNION ALL SELECT 2 AS id, 'b' AS val"
            ),
            unique_key="id",
            side="left",
            expected_unequal_samples=(
                RowDiffSampleRow(
                    key_values=(("id", 1),),
                    changed_cells=(RowDiffSampleCell(name="val", left_value="a", right_value="x"),),
                ),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_relations_when_sampling_unequal_rows_then_returns_expected_examples(
    test_case: BigQueryRowDiffSampleTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    left_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="left_t",
    )
    right_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="right_t",
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    unequal_samples: tuple[RowDiffSampleRow, ...] = adapter.sample_unequal_rows(
        connection,
        left=left_name,
        right=right_name,
        unique_key=test_case.unique_key,
        limit=5,
    )

    assert unequal_samples == test_case.expected_unequal_samples


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRowDiffSampleTestCase(
            description="returns side only key samples",
            left_sql=(
                "CREATE OR REPLACE TABLE left_t AS "
                "SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val"
            ),
            right_sql=(
                "CREATE OR REPLACE TABLE right_t AS "
                "SELECT 2 AS id, 'b' AS val UNION ALL SELECT 3 AS id, 'c' AS val"
            ),
            unique_key="id",
            side="left",
            expected_side_only_samples=((("id", 1),),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_relations_when_sampling_side_only_rows_then_returns_expected_examples(
    test_case: BigQueryRowDiffSampleTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    left_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="left_t",
    )
    right_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="right_t",
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    side_only_samples: tuple[tuple[tuple[str, object], ...], ...] = adapter.sample_side_only_rows(
        connection,
        left=left_name,
        right=right_name,
        unique_key=test_case.unique_key,
        side=test_case.side,
        limit=5,
    )

    assert side_only_samples == test_case.expected_side_only_samples


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryBuildFlowTestCase(
            description="loads seed csv and replaces table from select sql",
            seed_csv="id,name\n1,alice\n2,bob\n",
            staging_sql="SELECT 3 AS id, 'carol' AS name",
            expected_rows=((3, "carol"),),
            expected_recorded_fragment="COPY WRITE_TRUNCATE",
            expected_statement_count=4,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_and_table_flow_when_materializing_then_returns_expected_rows(
    test_case: BigQueryBuildFlowTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
    tmp_path: Path,
) -> None:
    seed_path: Path = write_seed_file(
        tmp_path=tmp_path,
        filename="seed.csv",
        contents=test_case.seed_csv,
    )
    seed_target: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="seed_data",
    )
    table_target: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="built_table",
    )
    staging_target: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="built_table__staging",
    )
    recorder: StatementRecorder = build_statement_recorder()

    adapter.load_seed(
        connection,
        destination=seed_target,
        file_path=seed_path,
        columns=(ColumnInfo(name="id", type="INTEGER"), ColumnInfo(name="name", type="VARCHAR")),
        statement_recorder=recorder,
    )
    adapter.create_table_as(
        connection,
        destination=table_target,
        sql=f"SELECT id, name FROM {seed_target} ORDER BY id",
        statement_recorder=recorder,
    )
    adapter.create_table_as(
        connection,
        destination=staging_target,
        sql=test_case.staging_sql,
        statement_recorder=recorder,
    )
    adapter.replace_table_from_relation(
        connection,
        destination=table_target,
        origin=staging_target,
        statement_recorder=recorder,
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, name FROM {table_target} ORDER BY id",
    )

    assert rows == test_case.expected_rows
    assert len(recorder.snapshot()) == test_case.expected_statement_count
    assert test_case.expected_recorded_fragment in recorder.snapshot()[-1].content


@pytest.mark.parametrize(
    "test_case",
    (
        BigQueryRelationReuseCopyTestCase(
            description="cheap reuse clones relation",
            hard_copy=False,
            destination_name="orders_cheap_reuse",
            expected_rows=((1, "alice"), (2, "bob")),
            expected_recorded_fragment=" CLONE ",
        ),
        BigQueryRelationReuseCopyTestCase(
            description="hard copy reuse uses CTAS",
            hard_copy=True,
            destination_name="orders_hard_reuse",
            expected_rows=((1, "alice"), (2, "bob")),
            expected_recorded_fragment=" AS SELECT * FROM ",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_reuse_origin_when_creating_relation_then_bigquery_uses_expected_copy_mode(
    test_case: BigQueryRelationReuseCopyTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    origin: str = qualified_name(
        project=bigquery_project, dataset=bigquery_dataset, name="orders_reuse_origin"
    )
    destination: str = qualified_name(
        project=bigquery_project, dataset=bigquery_dataset, name=test_case.destination_name
    )
    recorder: StatementRecorder = build_statement_recorder()
    adapter.execute(
        connection,
        f"CREATE OR REPLACE TABLE {origin} AS "
        "SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2, 'bob'",
    )

    create_relation_from_reuse_origin(
        adapter=adapter,
        connection=connection,
        origin_relation=origin,
        destination_relation=destination,
        hard_copy=test_case.hard_copy,
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
        BigQueryMergeTestCase(
            description="merges source rows into target table",
            target_setup_sql=(
                "CREATE OR REPLACE TABLE merge_target (id INT64, val STRING)",
                "INSERT INTO merge_target VALUES (1, 'old'), (2, 'keep')",
            ),
            source_sql=("SELECT 1 AS id, 'new' AS val UNION ALL SELECT 3 AS id, 'add' AS val"),
            unique_key="id",
            expected_rows=((1, "new"), (2, "keep"), (3, "add")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_merge_source_when_merging_then_target_matches_expected_rows(
    test_case: BigQueryMergeTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    target_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="merge_target",
    )
    setup_sql: tuple[str, ...] = tuple(
        statement.replace("merge_target", target_name) for statement in test_case.target_setup_sql
    )
    execute_statements(adapter=adapter, connection=connection, statements=setup_sql)

    adapter.merge(
        connection,
        destination=target_name,
        sql=test_case.source_sql,
        unique_key=test_case.unique_key,
        statement_recorder=build_statement_recorder(),
    )
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, val FROM {target_name} ORDER BY id",
    )

    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryDeleteInsertCursorTestCase(
            description="cursor delete insert replaces bounded window with native merge",
            target_setup_sql=(
                "CREATE OR REPLACE TABLE __target__ (id INT64, event_time TIMESTAMP, val STRING)",
                "INSERT INTO __target__ VALUES "
                "(1, TIMESTAMP '2026-01-01 00:00:00', 'old'), "
                "(2, TIMESTAMP '2026-01-03 00:00:00', 'keep')",
            ),
            source_sql=(
                "SELECT 1 AS id, TIMESTAMP '2026-01-01 00:00:00' AS event_time, 'new' AS val"
            ),
            cursor_column="event_time",
            cursor_start="2026-01-01T00:00:00",
            cursor_end="2026-01-02T00:00:00",
            columns=("id", "event_time", "val"),
            expected_rows=((1, "new"), (2, "keep")),
            expected_recorded_fragment="MERGE",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_window_when_delete_inserting_then_bigquery_uses_merge(
    test_case: BigQueryDeleteInsertCursorTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    target_name: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="events",
    )
    setup_sql: tuple[str, ...] = tuple(
        statement.replace("__target__", target_name) for statement in test_case.target_setup_sql
    )
    execute_statements(adapter=adapter, connection=connection, statements=setup_sql)
    recorder: StatementRecorder = build_statement_recorder()

    adapter.delete_insert_cursor(
        connection,
        destination=target_name,
        sql=test_case.source_sql,
        cursor_column=test_case.cursor_column,
        cursor_start=test_case.cursor_start,
        cursor_end=test_case.cursor_end,
        columns=test_case.columns,
        statement_recorder=recorder,
    )
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, val FROM {target_name} ORDER BY id",
    )

    assert rows == test_case.expected_rows
    assert test_case.expected_recorded_fragment in recorder.snapshot()[0].content


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryFingerprintTestCase(
            description="base64 multiline sql round trips",
            query_sql="SELECT 1 AS id\nUNION ALL SELECT 2 AS id",
            expected_model_name="fingerprint_model",
            expected_target_name="fingerprint_model",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_row_when_written_to_bigquery_then_base64_sql_round_trips(
    test_case: BigQueryFingerprintTestCase,
    adapter: BigQueryAdapter,
    connection: Any,
    bigquery_project: str,
    bigquery_dataset: str,
) -> None:
    fingerprint: Fingerprint = Fingerprint(
        node_type="model",
        node_name=test_case.expected_model_name,
        target_database=bigquery_project,
        target_schema=bigquery_dataset,
        target_name=test_case.expected_target_name,
        run_id="run-1",
        definition_hash="definition-hash",
        schema_fingerprint="schema-hash",
        definition=test_case.query_sql,
        ts=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    )

    write_fingerprint(
        connection=connection,
        execute=adapter.execute,
        database=bigquery_project,
        schema=bigquery_dataset,
        fingerprint=fingerprint,
        render_qualified_name=adapter.render_qualified_name,
        render_framework_type=adapter.render_framework_type,
    )

    fingerprint_set: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=adapter.execute,
        table_exists=adapter.relation_exists(
            connection,
            database=bigquery_project,
            schema=bigquery_dataset,
            name=FINGERPRINT_TABLE_NAME,
        ),
        database=bigquery_project,
        schema=bigquery_dataset,
        render_qualified_name=adapter.render_qualified_name,
        render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
    )
    fingerprint_table: str = qualified_name(
        project=bigquery_project,
        dataset=bigquery_dataset,
        name="_sqlbuild_fingerprints",
    )
    raw_rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=(
            f"SELECT definition_b64 FROM {fingerprint_table} WHERE node_name = 'fingerprint_model'"
        ),
    )

    actual_query_sql: str = fingerprint_set.fingerprints[test_case.expected_model_name].definition
    assert actual_query_sql == test_case.query_sql
    assert raw_rows == ((base64.b64encode(test_case.query_sql.encode("utf-8")).decode("ascii"),),)
