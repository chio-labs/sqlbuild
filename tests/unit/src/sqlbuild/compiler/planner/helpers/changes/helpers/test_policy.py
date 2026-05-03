from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.helpers.changes.helpers.policy import (
    resolve_query_change_backfill,
    resolve_schema_change_backfill,
)
from sqlbuild.compiler.planner.models import BackfillResult, SchemaFinding
from sqlbuild.compiler.planner.types import BackfillAction, SchemaChangeKind, SchemaColumnSource
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes.helpers._test_types import (
    ResolveBackfillTestCase,
    ResolveSchemaBackfillTestCase,
)

RESOLVE_QUERY_BACKFILL_TEST_CASES: list[ResolveBackfillTestCase] = [
    ResolveBackfillTestCase(
        description="returns full for full policy",
        raw_value="full",
        expected_result=BackfillResult(action=BackfillAction.FULL),
    ),
    ResolveBackfillTestCase(
        description="returns bounded with duration for bounded policy",
        raw_value="bounded(30d)",
        expected_result=BackfillResult(action=BackfillAction.BOUNDED, duration="30d"),
    ),
    ResolveBackfillTestCase(
        description="returns warn only for null policy",
        raw_value=None,
        expected_result=BackfillResult(action=BackfillAction.WARN_ONLY),
    ),
    ResolveBackfillTestCase(
        description="returns warn only for unrecognized policy value",
        raw_value="unknown",
        expected_result=BackfillResult(action=BackfillAction.WARN_ONLY),
    ),
]

RESOLVE_SCHEMA_BACKFILL_TEST_CASES: list[ResolveSchemaBackfillTestCase] = [
    ResolveSchemaBackfillTestCase(
        description="resolves add column policy from schema change backfill",
        schema_change_backfill={"add_column": "bounded(7d)"},
        findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_ADDED,
                column_name="status",
                source=SchemaColumnSource.YML,
                expected_type="VARCHAR",
            ),
        ),
        expected_result=BackfillResult(action=BackfillAction.BOUNDED, duration="7d"),
    ),
    ResolveSchemaBackfillTestCase(
        description="picks most aggressive across multiple findings",
        schema_change_backfill={"add_column": "bounded(7d)", "type_change": "full"},
        findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_ADDED,
                column_name="status",
                source=SchemaColumnSource.YML,
                expected_type="VARCHAR",
            ),
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                column_name="id",
                source=SchemaColumnSource.YML,
                expected_type="BIGINT",
                actual_type="INTEGER",
            ),
        ),
        expected_result=BackfillResult(action=BackfillAction.FULL),
    ),
    ResolveSchemaBackfillTestCase(
        description="returns warn only when no policy matches findings",
        schema_change_backfill={},
        findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_ADDED,
                column_name="status",
                source=SchemaColumnSource.YML,
                expected_type="VARCHAR",
            ),
        ),
        expected_result=BackfillResult(action=BackfillAction.WARN_ONLY),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_QUERY_BACKFILL_TEST_CASES,
    ids=[case.description for case in RESOLVE_QUERY_BACKFILL_TEST_CASES],
)
def test_given_policy_when_resolving_query_backfill_then_returns_expected(
    test_case: ResolveBackfillTestCase,
) -> None:
    result: BackfillResult = resolve_query_change_backfill(
        query_change_backfill=test_case.raw_value,
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_SCHEMA_BACKFILL_TEST_CASES,
    ids=[case.description for case in RESOLVE_SCHEMA_BACKFILL_TEST_CASES],
)
def test_given_findings_when_resolving_schema_backfill_then_returns_expected(
    test_case: ResolveSchemaBackfillTestCase,
) -> None:
    result: BackfillResult = resolve_schema_change_backfill(
        schema_change_backfill=test_case.schema_change_backfill,
        findings=test_case.findings,
    )

    assert result == test_case.expected_result
