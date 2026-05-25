"""State schema validation helper functions."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.versioned.state.constants import STATE_TABLES
from sqlbuild.versioned.state.models import (
    StateSchemaValidationIssue,
    StateSchemaValidationResult,
)
from sqlbuild.versioned.state.types import StateColumnType, StateSchemaValidationIssueKind


def build_validation_result(
    *,
    existing_tables: set[str],
    columns_by_table: dict[str, dict[str, str]],
    expected_columns: dict[str, dict[str, StateColumnType]],
    type_matches: Callable[[str, StateColumnType], bool],
) -> StateSchemaValidationResult:
    """Build validation issues for required tables and columns."""

    issues: list[StateSchemaValidationIssue] = []
    table_name: str
    for table_name in STATE_TABLES:
        if table_name not in existing_tables:
            issues.append(
                StateSchemaValidationIssue(
                    kind=StateSchemaValidationIssueKind.MISSING_TABLE,
                    table_name=table_name,
                    message=f"Missing state table: {table_name}",
                )
            )
            continue
        column_name: str
        expected_type: StateColumnType
        actual_columns: dict[str, str] = columns_by_table.get(table_name, {})
        for column_name, expected_type in expected_columns[table_name].items():
            actual_type: str | None = actual_columns.get(column_name)
            if actual_type is None:
                issues.append(
                    StateSchemaValidationIssue(
                        kind=StateSchemaValidationIssueKind.MISSING_COLUMN,
                        table_name=table_name,
                        column_name=column_name,
                        message=f"Missing state column: {table_name}.{column_name}",
                    )
                )
                continue
            if not type_matches(actual_type, expected_type):
                issues.append(
                    StateSchemaValidationIssue(
                        kind=StateSchemaValidationIssueKind.WRONG_TYPE,
                        table_name=table_name,
                        column_name=column_name,
                        message=(
                            f"Wrong state column type: {table_name}.{column_name} "
                            f"expected {expected_type.value}, got {actual_type}"
                        ),
                    )
                )
    return StateSchemaValidationResult(issues=tuple(issues))
