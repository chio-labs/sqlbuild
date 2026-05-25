from __future__ import annotations

import pytest

from sqlbuild.versioned.state.constants import STATE_TABLE_COLUMNS
from sqlbuild.versioned.state.helpers.validation import build_validation_result
from sqlbuild.versioned.state.models import StateSchemaValidationResult
from sqlbuild.versioned.state.types import StateSchemaValidationIssueKind
from tests.unit.src.sqlbuild.versioned.state.helpers._test_types import (
    StateValidationHelperTestCase,
)
from tests.unit.src.sqlbuild.versioned.state.helpers.helpers import state_type_matches_for_test

TEST_CASES: list[StateValidationHelperTestCase] = [
    StateValidationHelperTestCase(
        description="accepts required tables and compatible column types",
        existing_tables={"state_versions", "state_migration_events"},
        columns_by_table={
            "state_versions": {
                "schema_version": "INTEGER",
                "sqlbuild_version": "VARCHAR",
                "updated_at": "TIMESTAMP",
            },
            "state_migration_events": {
                "event_id": "VARCHAR",
                "action": "VARCHAR",
                "backup_id": "VARCHAR",
                "status": "VARCHAR",
                "message": "VARCHAR",
                "created_at": "TIMESTAMP",
            },
        },
        expected_issue_kinds=(),
    ),
    StateValidationHelperTestCase(
        description="reports missing table",
        existing_tables={"state_versions"},
        columns_by_table={
            "state_versions": {
                "schema_version": "INTEGER",
                "sqlbuild_version": "VARCHAR",
                "updated_at": "TIMESTAMP",
            },
        },
        expected_issue_kinds=(StateSchemaValidationIssueKind.MISSING_TABLE,),
    ),
    StateValidationHelperTestCase(
        description="reports missing column and wrong type",
        existing_tables={"state_versions", "state_migration_events"},
        columns_by_table={
            "state_versions": {
                "schema_version": "VARCHAR",
                "updated_at": "TIMESTAMP",
            },
            "state_migration_events": {
                "event_id": "VARCHAR",
                "action": "VARCHAR",
                "backup_id": "VARCHAR",
                "status": "VARCHAR",
                "message": "VARCHAR",
                "created_at": "TIMESTAMP",
            },
        },
        expected_issue_kinds=(
            StateSchemaValidationIssueKind.WRONG_TYPE,
            StateSchemaValidationIssueKind.MISSING_COLUMN,
        ),
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_state_schema_metadata_when_validating_then_reports_expected_issues(
    test_case: StateValidationHelperTestCase,
) -> None:
    result: StateSchemaValidationResult = build_validation_result(
        existing_tables=test_case.existing_tables,
        columns_by_table=test_case.columns_by_table,
        expected_columns=STATE_TABLE_COLUMNS,
        type_matches=state_type_matches_for_test,
    )

    assert tuple(issue.kind for issue in result.issues) == test_case.expected_issue_kinds
    assert result.valid is (not test_case.expected_issue_kinds)
