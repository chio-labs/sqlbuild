from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.output.strategy import resolve_schema_actions
from sqlbuild.compiler.planner.models import SchemaAction, SchemaFinding
from sqlbuild.compiler.planner.types import (
    OnSchemaChange,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    ResolveSchemaActionsTestCase,
)

_ADDED_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_ADDED,
    column_name="status",
    source=SchemaColumnSource.YML,
    expected_type="VARCHAR",
)

_REMOVED_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_REMOVED,
    column_name="old_col",
    source=SchemaColumnSource.YML,
    actual_type="INTEGER",
)

_TYPE_CHANGED_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
    column_name="amount",
    source=SchemaColumnSource.YML,
    expected_type="DECIMAL",
    actual_type="INTEGER",
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveSchemaActionsTestCase(
            description="ignore produces no actions regardless of findings",
            schema_findings=(_ADDED_FINDING, _REMOVED_FINDING, _TYPE_CHANGED_FINDING),
            on_schema_change=OnSchemaChange.IGNORE,
            expected_actions=(),
        ),
        ResolveSchemaActionsTestCase(
            description="fail produces no actions regardless of findings",
            schema_findings=(_ADDED_FINDING, _REMOVED_FINDING),
            on_schema_change=OnSchemaChange.FAIL,
            expected_actions=(),
        ),
        ResolveSchemaActionsTestCase(
            description="append_new_columns adds only new columns",
            schema_findings=(_ADDED_FINDING, _REMOVED_FINDING, _TYPE_CHANGED_FINDING),
            on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
            expected_actions=(
                SchemaAction(
                    kind=SchemaActionKind.ADD_COLUMN,
                    column_name="status",
                    column_type="VARCHAR",
                ),
            ),
        ),
        ResolveSchemaActionsTestCase(
            description="sync_all_columns handles add drop and alter",
            schema_findings=(_ADDED_FINDING, _REMOVED_FINDING, _TYPE_CHANGED_FINDING),
            on_schema_change=OnSchemaChange.SYNC_ALL_COLUMNS,
            expected_actions=(
                SchemaAction(
                    kind=SchemaActionKind.ADD_COLUMN,
                    column_name="status",
                    column_type="VARCHAR",
                ),
                SchemaAction(
                    kind=SchemaActionKind.DROP_COLUMN,
                    column_name="old_col",
                ),
                SchemaAction(
                    kind=SchemaActionKind.ALTER_COLUMN_TYPE,
                    column_name="amount",
                    column_type="DECIMAL",
                ),
            ),
        ),
        ResolveSchemaActionsTestCase(
            description="default on_schema_change uses append_new_columns",
            schema_findings=(_ADDED_FINDING, _REMOVED_FINDING),
            on_schema_change=None,
            expected_actions=(
                SchemaAction(
                    kind=SchemaActionKind.ADD_COLUMN,
                    column_name="status",
                    column_type="VARCHAR",
                ),
            ),
        ),
        ResolveSchemaActionsTestCase(
            description="empty findings produces no actions",
            schema_findings=(),
            on_schema_change=OnSchemaChange.SYNC_ALL_COLUMNS,
            expected_actions=(),
        ),
        ResolveSchemaActionsTestCase(
            description=("append_new_columns ignores type changes and removals"),
            schema_findings=(_REMOVED_FINDING, _TYPE_CHANGED_FINDING),
            on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
            expected_actions=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_findings_and_policy_when_resolving_schema_actions_then_returns_expected(
    test_case: ResolveSchemaActionsTestCase,
) -> None:
    result: tuple[SchemaAction, ...] = resolve_schema_actions(
        schema_findings=test_case.schema_findings,
        on_schema_change=test_case.on_schema_change,
    )

    assert result == test_case.expected_actions
