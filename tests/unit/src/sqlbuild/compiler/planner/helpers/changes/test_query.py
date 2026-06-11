from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.changes.query import detect_query_change
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes._test_types import (
    DetectQueryChangeTestCase,
)

DETECT_QUERY_CHANGE_TEST_CASES: list[DetectQueryChangeTestCase] = [
    DetectQueryChangeTestCase(
        description="detects no change when query hashes match",
        compiled_query_hash="abc",
        fingerprint_query_hash="abc",
        expected_changed=False,
    ),
    DetectQueryChangeTestCase(
        description="detects change when query hashes differ",
        compiled_query_hash="abc",
        fingerprint_query_hash="def",
        expected_changed=True,
    ),
]

_STUB_TS: datetime = datetime(2026, 1, 15, 12, 0, 0)


@pytest.mark.parametrize(
    "test_case",
    DETECT_QUERY_CHANGE_TEST_CASES,
    ids=[case.description for case in DETECT_QUERY_CHANGE_TEST_CASES],
)
def test_given_hashes_when_detecting_query_change_then_returns_expected(
    test_case: DetectQueryChangeTestCase,
) -> None:
    fingerprint: Fingerprint = Fingerprint(
        node_type="model",
        node_name="test",
        target_database=None,
        target_schema=None,
        target_name="test",
        run_id="run_001",
        definition_hash=test_case.fingerprint_query_hash,
        schema_fingerprint="schema_a",
        definition="SELECT 1",
        ts=_STUB_TS,
    )
    result: bool = detect_query_change(
        compiled_query_hash=test_case.compiled_query_hash,
        fingerprint=fingerprint,
    )

    assert result == test_case.expected_changed
