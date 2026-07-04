from __future__ import annotations

import base64
from datetime import datetime

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from tests.unit.src.sqlbuild.compiler.fingerprints.main._test_types import (
    ReadLatestFingerprintsErrorTestCase,
    ReadLatestFingerprintsRendererTestCase,
    ReadLatestFingerprintsTestCase,
    WriteFingerprintIndexTestCase,
)
from tests.unit.src.sqlbuild.compiler.fingerprints.main.helpers import (
    FakeFingerprintExecute,
    FakeFingerprintWriteExecute,
    render_create_fingerprint_index_sqls,
    render_qualified_name,
    render_read_latest_sql,
    render_sentinel_read_latest_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestFingerprintsTestCase(
            description="decodes query SQL and metadata JSON from latest fingerprint row",
            rows=[
                (
                    "model",
                    "orders",
                    None,
                    "main",
                    "orders",
                    "run_001",
                    "definition_hash",
                    "version_hash",
                    "schema_hash",
                    base64.b64encode(b"SELECT 1 AS order_id").decode("ascii"),
                    base64.b64encode(b'{"config":{"materialized":"table"}}').decode("ascii"),
                    datetime(2026, 1, 15, 12, 0, 0),
                )
            ],
            expected_model_name="orders",
            expected_version_hash="version_hash",
            expected_query_sql="SELECT 1 AS order_id",
            expected_metadata_json='{"config":{"materialized":"table"}}',
        )
    ],
    ids=lambda case: case.description,
)
def test_given_encoded_fingerprint_row_when_reading_then_decodes_query_and_metadata(
    test_case: ReadLatestFingerprintsTestCase,
) -> None:
    fingerprints: FingerprintSet = read_latest_fingerprints(
        connection=object(),
        execute=FakeFingerprintExecute(rows=test_case.rows),
        table_exists=True,
        database=None,
        schema="main",
        render_qualified_name=render_qualified_name,
        render_read_latest_sql=render_read_latest_sql,
    )

    fingerprint: Fingerprint = fingerprints.fingerprints[test_case.expected_model_name]
    assert fingerprints.fingerprints_by_identity is not None
    assert (
        fingerprints.fingerprints_by_identity[("model", test_case.expected_model_name)]
        is fingerprint
    )
    assert fingerprint.version_hash == test_case.expected_version_hash
    assert fingerprint.definition == test_case.expected_query_sql
    assert fingerprint.metadata_json == test_case.expected_metadata_json


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestFingerprintsRendererTestCase(
            description="uses injected latest-read SQL renderer",
            expected_executed_sql="SELECT 'sentinel latest fingerprint sql'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_latest_sql_renderer_when_reading_then_executes_renderer_sql(
    test_case: ReadLatestFingerprintsRendererTestCase,
) -> None:
    execute: FakeFingerprintExecute = FakeFingerprintExecute(rows=[])

    read_latest_fingerprints(
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
        WriteFingerprintIndexTestCase(
            description="creates index before inserting fingerprint row",
            expected_index_sql="CREATE INDEX sentinel_fingerprint_idx",
            expected_insert_prefix="INSERT INTO main._sqlbuild_fingerprints",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_index_renderer_when_writing_fingerprint_then_executes_index_before_insert(
    test_case: WriteFingerprintIndexTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    execute: FakeFingerprintWriteExecute = FakeFingerprintWriteExecute()

    write_fingerprint(
        connection=object(),
        execute=execute,
        database=None,
        schema="main",
        fingerprint=Fingerprint(
            node_type="model",
            node_name="orders",
            target_database=None,
            target_schema="main",
            target_name="orders",
            run_id="run_001",
            definition_hash="definition_hash",
            version_hash="version_hash",
            schema_fingerprint="schema_hash",
            definition="SELECT 1",
            metadata_json="{}",
            ts=datetime(2026, 1, 15, 12, 0, 0),
        ),
        render_qualified_name=render_qualified_name,
        render_framework_type=adapter.render_framework_type,
        render_create_index_sqls=render_create_fingerprint_index_sqls,
    )

    assert execute.executed_sql[1] == test_case.expected_index_sql
    assert execute.executed_sql[2].startswith(test_case.expected_insert_prefix)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestFingerprintsErrorTestCase(
            description="old fingerprint table schema read failure gives operator guidance",
            read_error=RuntimeError("missing column metadata_json_b64"),
            expected_message_fragment="delete or rebuild the SQLBuild fingerprint table",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_read_failure_when_reading_fingerprints_then_raises_operator_guidance(
    test_case: ReadLatestFingerprintsErrorTestCase,
) -> None:
    with pytest.raises(FingerprintInputError) as exc_info:
        read_latest_fingerprints(
            connection=object(),
            execute=FakeFingerprintExecute(rows=[], read_error=test_case.read_error),
            table_exists=True,
            database=None,
            schema="main",
            render_qualified_name=render_qualified_name,
            render_read_latest_sql=render_read_latest_sql,
        )

    assert test_case.expected_message_fragment in str(exc_info.value)
