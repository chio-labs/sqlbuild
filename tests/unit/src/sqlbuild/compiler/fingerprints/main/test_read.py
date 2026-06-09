from __future__ import annotations

import base64
from datetime import datetime

import pytest

from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from tests.unit.src.sqlbuild.compiler.fingerprints.main._test_types import (
    ReadLatestFingerprintsErrorTestCase,
    ReadLatestFingerprintsTestCase,
)
from tests.unit.src.sqlbuild.compiler.fingerprints.main.helpers import (
    FakeFingerprintExecute,
    fingerprint_table_relation_exists,
    render_qualified_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestFingerprintsTestCase(
            description="decodes query SQL and metadata JSON from latest fingerprint row",
            rows=[
                (
                    "orders",
                    None,
                    "main",
                    "orders",
                    "run_001",
                    "query_hash",
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
    ids=["decodes query SQL and metadata JSON from latest fingerprint row"],
)
def test_given_encoded_fingerprint_row_when_reading_then_decodes_query_and_metadata(
    test_case: ReadLatestFingerprintsTestCase,
) -> None:
    fingerprints: FingerprintSet = read_latest_fingerprints(
        connection=object(),
        execute=FakeFingerprintExecute(rows=test_case.rows),
        relation_exists=fingerprint_table_relation_exists,
        database=None,
        schema="main",
        render_qualified_name=render_qualified_name,
    )

    fingerprint: Fingerprint = fingerprints.fingerprints[test_case.expected_model_name]
    assert fingerprint.version_hash == test_case.expected_version_hash
    assert fingerprint.query_sql == test_case.expected_query_sql
    assert fingerprint.metadata_json == test_case.expected_metadata_json


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestFingerprintsErrorTestCase(
            description="old fingerprint table schema read failure gives operator guidance",
            read_error=RuntimeError("missing column metadata_json_b64"),
            expected_message_fragment="delete or rebuild the SQLBuild fingerprint table",
        )
    ],
    ids=["old fingerprint table schema read failure gives operator guidance"],
)
def test_given_read_failure_when_reading_fingerprints_then_raises_operator_guidance(
    test_case: ReadLatestFingerprintsErrorTestCase,
) -> None:
    with pytest.raises(FingerprintInputError) as exc_info:
        read_latest_fingerprints(
            connection=object(),
            execute=FakeFingerprintExecute(rows=[], read_error=test_case.read_error),
            relation_exists=fingerprint_table_relation_exists,
            database=None,
            schema="main",
            render_qualified_name=render_qualified_name,
        )

    assert test_case.expected_message_fragment in str(exc_info.value)
