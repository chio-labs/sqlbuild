from __future__ import annotations

import pytest

from sqlbuild.versioned.state.constants import STATE_TABLE_COLUMNS, STATE_TABLE_INDEXES
from sqlbuild.versioned.state.helpers.validation import build_validation_result
from sqlbuild.versioned.state.models import StateSchemaValidationResult
from sqlbuild.versioned.state.types import StateSchemaValidationIssueKind
from tests.unit.src.sqlbuild.versioned.state.helpers._test_types import (
    StateValidationHelperTestCase,
)
from tests.unit.src.sqlbuild.versioned.state.helpers.helpers import (
    state_columns_for_test,
    state_indexes_for_test,
    state_type_matches_for_test,
)

VALID_COLUMNS_BY_TABLE: dict[str, dict[str, str]] = state_columns_for_test(STATE_TABLE_COLUMNS)
VALID_INDEXES_BY_TABLE: dict[str, set[str]] = state_indexes_for_test(STATE_TABLE_INDEXES)

TEST_CASES: list[StateValidationHelperTestCase] = [
    StateValidationHelperTestCase(
        description="accepts required tables and compatible column types",
        existing_tables=set(STATE_TABLE_COLUMNS),
        columns_by_table=VALID_COLUMNS_BY_TABLE,
        existing_indexes_by_table=VALID_INDEXES_BY_TABLE,
        expected_issue_kinds=(),
    ),
    StateValidationHelperTestCase(
        description="reports missing table",
        existing_tables=set(STATE_TABLE_COLUMNS) - {"state_migration_events"},
        columns_by_table={
            table_name: columns
            for table_name, columns in VALID_COLUMNS_BY_TABLE.items()
            if table_name != "state_migration_events"
        },
        existing_indexes_by_table=VALID_INDEXES_BY_TABLE,
        expected_issue_kinds=(StateSchemaValidationIssueKind.MISSING_TABLE,),
    ),
    StateValidationHelperTestCase(
        description="reports missing column and wrong type",
        existing_tables=set(STATE_TABLE_COLUMNS),
        columns_by_table={
            **VALID_COLUMNS_BY_TABLE,
            "state_versions": {
                "schema_version": "VARCHAR",
                "updated_at": "TIMESTAMP",
            },
        },
        existing_indexes_by_table=VALID_INDEXES_BY_TABLE,
        expected_issue_kinds=(
            StateSchemaValidationIssueKind.WRONG_TYPE,
            StateSchemaValidationIssueKind.MISSING_COLUMN,
        ),
    ),
    StateValidationHelperTestCase(
        description="reports missing index",
        existing_tables=set(STATE_TABLE_COLUMNS),
        columns_by_table=VALID_COLUMNS_BY_TABLE,
        existing_indexes_by_table={
            table_name: indexes
            for table_name, indexes in VALID_INDEXES_BY_TABLE.items()
            if table_name != "locks"
        },
        expected_issue_kinds=(StateSchemaValidationIssueKind.MISSING_INDEX,),
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
        expected_indexes=STATE_TABLE_INDEXES,
        existing_indexes_by_table=test_case.existing_indexes_by_table,
    )

    assert tuple(issue.kind for issue in result.issues) == test_case.expected_issue_kinds
    assert result.valid is (not test_case.expected_issue_kinds)
