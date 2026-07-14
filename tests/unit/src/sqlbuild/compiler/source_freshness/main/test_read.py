from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessInputError
from sqlbuild.compiler.source_freshness.main.read import read_latest_source_freshness
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_records
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    SourceFreshnessRenderers,
    SourceFreshnessSet,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    ReadLatestSourceFreshnessErrorTestCase,
    ReadLatestSourceFreshnessRendererTestCase,
    ReadLatestSourceFreshnessTestCase,
    WriteSourceFreshnessIndexTestCase,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main.helpers import (
    FakeSourceFreshnessExecute,
    FakeSourceFreshnessWriteExecute,
    render_create_source_freshness_index_sqls,
    render_qualified_name,
    render_read_latest_sql,
    render_sentinel_read_latest_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestSourceFreshnessTestCase(
            description="parses observed_at from string rows",
            rows=[
                (
                    "raw.orders",
                    None,
                    "raw",
                    "orders",
                    "run_001",
                    "adapter_metadata",
                    "timestamp",
                    "2026-01-15T12:00:00",
                    "hash_orders",
                    "2026-01-15T12:05:00",
                )
            ],
            expected_source_name="raw.orders",
            expected_observed_at_iso="2026-01-15T12:05:00",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_string_timestamp_row_when_reading_source_freshness_then_parses_timestamp(
    test_case: ReadLatestSourceFreshnessTestCase,
) -> None:
    result: SourceFreshnessSet = read_latest_source_freshness(
        connection=object(),
        execute=FakeSourceFreshnessExecute(rows=test_case.rows),
        table_exists=True,
        database=None,
        schema="main",
        render_qualified_name=render_qualified_name,
        render_read_latest_sql=render_read_latest_sql,
    )

    identity: SourceFreshnessIdentity = SourceFreshnessIdentity(
        test_case.expected_source_name, None, "raw", "orders"
    )
    record: SourceFreshnessRecord = result.records[identity]
    assert record.observed_at == datetime.fromisoformat(test_case.expected_observed_at_iso)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestSourceFreshnessRendererTestCase(
            description="uses injected latest-read SQL renderer",
            expected_executed_sql="SELECT 'sentinel latest source freshness sql'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_latest_sql_renderer_when_reading_source_freshness_then_executes_renderer_sql(
    test_case: ReadLatestSourceFreshnessRendererTestCase,
) -> None:
    execute: FakeSourceFreshnessExecute = FakeSourceFreshnessExecute(rows=[])

    read_latest_source_freshness(
        connection=object(),
        execute=execute,
        table_exists=True,
        database=None,
        schema="main",
        render_qualified_name=render_qualified_name,
        render_read_latest_sql=render_sentinel_read_latest_sql,
    )

    assert execute.executed_sql == [test_case.expected_executed_sql]


@pytest.mark.parametrize(
    "test_case",
    [
        WriteSourceFreshnessIndexTestCase(
            description=(
                "creates index once before inserting source freshness rows in one statement"
            ),
            expected_index_sql="CREATE INDEX sentinel_source_freshness_idx",
            expected_insert_prefix="INSERT INTO main._sqlbuild_source_freshness",
            expected_statement_count=3,
            expected_values_separator="), (",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_index_renderer_when_writing_source_freshness_then_batches_inserts_after_index(
    test_case: WriteSourceFreshnessIndexTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    execute: FakeSourceFreshnessWriteExecute = FakeSourceFreshnessWriteExecute()

    write_source_freshness_records(
        connection=object(),
        execute=execute,
        database=None,
        schema="main",
        records=(
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw",
                target_name="orders",
                run_id="run_001",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T12:00:00",
                data_version_hash="hash_orders",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
            SourceFreshnessRecord(
                source_name="raw.customers",
                target_database=None,
                target_schema="raw",
                target_name="customers",
                run_id="run_001",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T12:10:00",
                data_version_hash="hash_customers",
                observed_at=datetime(2026, 1, 15, 12, 15, 0),
            ),
        ),
        renderers=SourceFreshnessRenderers(
            render_qualified_name=render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
            render_create_index_sqls=render_create_source_freshness_index_sqls,
        ),
    )

    assert len(execute.executed_sql) == test_case.expected_statement_count
    assert execute.executed_sql[1] == test_case.expected_index_sql
    assert execute.executed_sql[2].startswith(test_case.expected_insert_prefix)
    assert test_case.expected_values_separator in execute.executed_sql[2]


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestSourceFreshnessErrorTestCase(
            description="old source freshness table schema read failure gives operator guidance",
            read_error=RuntimeError("missing column data_version_hash"),
            expected_message_fragment="delete or rebuild the SQLBuild source freshness table",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_read_failure_when_reading_source_freshness_then_raises_operator_guidance(
    test_case: ReadLatestSourceFreshnessErrorTestCase,
) -> None:
    with pytest.raises(SourceFreshnessInputError) as exc_info:
        read_latest_source_freshness(
            connection=object(),
            execute=FakeSourceFreshnessExecute(rows=[], read_error=test_case.read_error),
            table_exists=True,
            database=None,
            schema="main",
            render_qualified_name=render_qualified_name,
            render_read_latest_sql=render_read_latest_sql,
        )

    assert test_case.expected_message_fragment in str(exc_info.value)
