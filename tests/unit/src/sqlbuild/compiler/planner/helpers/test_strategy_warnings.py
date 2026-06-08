from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.helpers.strategy import build_model_warnings
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlanWarning,
    SchemaAction,
    SchemaFinding,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    MaterializationType,
    OnSchemaChange,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
    WarningSeverity,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    BuildModelWarningsTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_warnings_change_result,
)

_ADDED_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_ADDED,
    column_name="status",
    source=SchemaColumnSource.YML,
    expected_type="VARCHAR",
)

_TYPE_CHANGED_YML_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
    column_name="amount",
    source=SchemaColumnSource.YML,
    expected_type="DECIMAL",
    actual_type="INTEGER",
)

_TYPE_CHANGED_SQLGLOT_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
    column_name="amount",
    source=SchemaColumnSource.SQLGLOT,
    expected_type="DECIMAL",
    actual_type="INTEGER",
)

_ADDED_SQLGLOT_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_ADDED,
    column_name="new_col",
    source=SchemaColumnSource.SQLGLOT,
    expected_type="VARCHAR",
)

_REMOVED_FINDING: SchemaFinding = SchemaFinding(
    kind=SchemaChangeKind.COLUMN_REMOVED,
    column_name="old_col",
    source=SchemaColumnSource.YML,
    actual_type="INTEGER",
)

_ADD_ACTION: SchemaAction = SchemaAction(
    kind=SchemaActionKind.ADD_COLUMN,
    column_name="status",
    column_type="VARCHAR",
)

BUILD_WARNINGS_TEST_CASES: list[BuildModelWarningsTestCase] = [
    BuildModelWarningsTestCase(
        description="on_schema_change fail with findings produces error",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.SCHEMA_CHANGED,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_ADDED_FINDING,),
        schema_actions=(),
        on_schema_change=OnSchemaChange.FAIL,
        type_enforcement=False,
        expected_severity=WarningSeverity.ERROR,
        expected_warning_count=1,
    ),
    BuildModelWarningsTestCase(
        description="enforced type mismatch produces warning",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.SCHEMA_CHANGED,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_TYPE_CHANGED_YML_FINDING,),
        schema_actions=(),
        on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
        type_enforcement=True,
        expected_severity=WarningSeverity.WARNING,
        expected_warning_count=1,
    ),
    BuildModelWarningsTestCase(
        description="sql_analysis type change produces info warning",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.SCHEMA_CHANGED,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_TYPE_CHANGED_SQLGLOT_FINDING,),
        schema_actions=(),
        on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
        type_enforcement=False,
        expected_severity=WarningSeverity.INFO,
        expected_warning_count=1,
    ),
    BuildModelWarningsTestCase(
        description="query changed without backfill policy produces warning",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.QUERY_CHANGED,
        query_changed=True,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(),
        schema_actions=(),
        on_schema_change=None,
        type_enforcement=False,
        expected_severity=WarningSeverity.WARNING,
        expected_warning_count=1,
    ),
    BuildModelWarningsTestCase(
        description="on_schema_change ignore with findings produces info",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.SCHEMA_CHANGED,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_ADDED_FINDING,),
        schema_actions=(),
        on_schema_change=OnSchemaChange.IGNORE,
        type_enforcement=False,
        expected_severity=WarningSeverity.INFO,
        expected_warning_count=1,
    ),
    BuildModelWarningsTestCase(
        description="no findings and no query change produces no warnings",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.NO_CHANGE,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(),
        schema_actions=(),
        on_schema_change=None,
        type_enforcement=False,
        expected_severity=None,
        expected_warning_count=0,
    ),
    BuildModelWarningsTestCase(
        description="sql_analysis added column produces info warning",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.SCHEMA_CHANGED,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_ADDED_SQLGLOT_FINDING,),
        schema_actions=(),
        on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
        type_enforcement=False,
        expected_severity=WarningSeverity.INFO,
        expected_warning_count=1,
    ),
    BuildModelWarningsTestCase(
        description="query changed with configured backfill produces no warning",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.QUERY_CHANGED,
        query_changed=True,
        backfill_action=BackfillAction.BOUNDED,
        schema_findings=(),
        schema_actions=(),
        on_schema_change=None,
        type_enforcement=False,
        expected_severity=None,
        expected_warning_count=0,
    ),
    BuildModelWarningsTestCase(
        description="query changed on table model produces no warn-only policy warning",
        model_name="orders",
        materialization_type=MaterializationType.TABLE,
        change_kind=ChangeKind.QUERY_CHANGED,
        query_changed=True,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(),
        schema_actions=(),
        on_schema_change=None,
        type_enforcement=False,
        expected_severity=None,
        expected_warning_count=0,
    ),
    BuildModelWarningsTestCase(
        description="column removed finding produces no warning",
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.SCHEMA_CHANGED,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_REMOVED_FINDING,),
        schema_actions=(),
        on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
        type_enforcement=False,
        expected_severity=None,
        expected_warning_count=0,
    ),
    BuildModelWarningsTestCase(
        description=(
            "enforced type mismatch and query change produce two warnings with mixed severities"
        ),
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.QUERY_CHANGED,
        query_changed=True,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_TYPE_CHANGED_YML_FINDING,),
        schema_actions=(),
        on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
        type_enforcement=True,
        expected_severity=None,
        expected_warning_count=2,
        expected_severities=(
            WarningSeverity.WARNING,
            WarningSeverity.WARNING,
        ),
    ),
    BuildModelWarningsTestCase(
        description=("enforced yml column added does not produce type mismatch warning"),
        model_name="orders",
        materialization_type=MaterializationType.INCREMENTAL,
        change_kind=ChangeKind.SCHEMA_CHANGED,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        schema_findings=(_ADDED_FINDING,),
        schema_actions=(_ADD_ACTION,),
        on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
        type_enforcement=True,
        expected_severity=None,
        expected_warning_count=0,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BUILD_WARNINGS_TEST_CASES,
    ids=[case.description for case in BUILD_WARNINGS_TEST_CASES],
)
def test_given_model_state_when_building_warnings_then_matches_expected(
    test_case: BuildModelWarningsTestCase,
) -> None:
    change_result: ChangeDetectionResult = build_warnings_change_result(test_case)

    result: tuple[PlanWarning, ...] = build_model_warnings(
        model_name=test_case.model_name,
        materialization_type=test_case.materialization_type,
        change_result=change_result,
        schema_actions=test_case.schema_actions,
        on_schema_change=test_case.on_schema_change,
        type_enforcement=test_case.type_enforcement,
    )

    assert len(result) == test_case.expected_warning_count
    actual_severities: tuple[WarningSeverity, ...] = tuple(w.severity for w in result)
    expected: tuple[WarningSeverity, ...]
    expected = test_case.expected_severities or (
        (test_case.expected_severity,) * test_case.expected_warning_count
        if test_case.expected_severity is not None
        else ()
    )
    assert actual_severities == expected
