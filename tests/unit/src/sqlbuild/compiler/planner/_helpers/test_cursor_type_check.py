"""Tests for warehouse cursor column type consistency checking."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.planner._helpers.output.cursor_type_check import (
    check_cursor_type_consistency,
)
from sqlbuild.compiler.planner.models import PlanWarning
from sqlbuild.compiler.planner.types import WarningSeverity
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    CursorTypeCheckTestCase,
)

_MODEL_NAME: str = "test_model"


@pytest.mark.parametrize(
    "test_case",
    [
        CursorTypeCheckTestCase(
            description="heuristic detects timestamp column with integer cursor_type",
            cursor_column="event_time",
            cursor_type="integer",
            warehouse_columns=(("event_time", "TIMESTAMP_NTZ"),),
            sql_analysis_enabled=False,
            expected_warning=True,
            expected_severity=WarningSeverity.WARNING,
            expected_message_fragment="appears to be timestamp",
        ),
        CursorTypeCheckTestCase(
            description="heuristic detects integer column with timestamp cursor_type",
            cursor_column="version_id",
            cursor_type="timestamp",
            warehouse_columns=(("version_id", "BIGINT"),),
            sql_analysis_enabled=False,
            expected_warning=True,
            expected_severity=WarningSeverity.WARNING,
            expected_message_fragment="appears to be integer",
        ),
        CursorTypeCheckTestCase(
            description="sql_analysis detects timestamp column with integer cursor_type",
            cursor_column="event_time",
            cursor_type="integer",
            warehouse_columns=(("event_time", "TIMESTAMP_NTZ"),),
            sql_analysis_enabled=True,
            expected_warning=True,
            expected_severity=WarningSeverity.ERROR,
            expected_message_fragment="which is timestamp",
        ),
        CursorTypeCheckTestCase(
            description="sql_analysis detects integer column with timestamp cursor_type",
            cursor_column="version_id",
            cursor_type="timestamp",
            warehouse_columns=(("version_id", "BIGINT"),),
            sql_analysis_enabled=True,
            expected_warning=True,
            expected_severity=WarningSeverity.ERROR,
            expected_message_fragment="which is integer",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_mismatched_cursor_type_when_checking_then_returns_warning(
    test_case: CursorTypeCheckTestCase,
) -> None:
    columns: tuple[ColumnInfo, ...] = tuple(
        ColumnInfo(name=name, type=col_type) for name, col_type in test_case.warehouse_columns
    )

    result: PlanWarning | None = check_cursor_type_consistency(
        model_name=_MODEL_NAME,
        cursor_column=test_case.cursor_column,
        cursor_type=test_case.cursor_type,
        warehouse_columns=columns,
        sql_analysis_enabled=test_case.sql_analysis_enabled,
    )

    assert result is not None
    assert result.severity == test_case.expected_severity
    assert test_case.expected_message_fragment is not None
    assert test_case.expected_message_fragment in result.message


@pytest.mark.parametrize(
    "test_case",
    [
        CursorTypeCheckTestCase(
            description="no cursor_column returns none",
            cursor_column=None,
            cursor_type="timestamp",
            warehouse_columns=(("event_time", "TIMESTAMP_NTZ"),),
            sql_analysis_enabled=False,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="no cursor_type returns none",
            cursor_column="event_time",
            cursor_type=None,
            warehouse_columns=(("event_time", "TIMESTAMP_NTZ"),),
            sql_analysis_enabled=False,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="cursor column not in warehouse returns none",
            cursor_column="event_time",
            cursor_type="timestamp",
            warehouse_columns=(("other_col", "VARCHAR"),),
            sql_analysis_enabled=False,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="matching timestamp type returns none with heuristic",
            cursor_column="event_time",
            cursor_type="timestamp",
            warehouse_columns=(("event_time", "TIMESTAMP_NTZ"),),
            sql_analysis_enabled=False,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="matching integer type returns none with heuristic",
            cursor_column="version_id",
            cursor_type="integer",
            warehouse_columns=(("version_id", "BIGINT"),),
            sql_analysis_enabled=False,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="matching timestamp type returns none with sql_analysis",
            cursor_column="event_time",
            cursor_type="timestamp",
            warehouse_columns=(("event_time", "TIMESTAMP_NTZ"),),
            sql_analysis_enabled=True,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="matching integer type returns none with sql_analysis",
            cursor_column="version_id",
            cursor_type="integer",
            warehouse_columns=(("version_id", "BIGINT"),),
            sql_analysis_enabled=True,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="unclassifiable warehouse type returns none with heuristic",
            cursor_column="payload",
            cursor_type="timestamp",
            warehouse_columns=(("payload", "VARCHAR"),),
            sql_analysis_enabled=False,
            expected_warning=False,
        ),
        CursorTypeCheckTestCase(
            description="case-insensitive column name match returns none for matching types",
            cursor_column="Event_Time",
            cursor_type="timestamp",
            warehouse_columns=(("event_time", "TIMESTAMP_NTZ"),),
            sql_analysis_enabled=False,
            expected_warning=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_consistent_or_uncheckable_cursor_type_when_checking_then_returns_none(
    test_case: CursorTypeCheckTestCase,
) -> None:
    columns: tuple[ColumnInfo, ...] = tuple(
        ColumnInfo(name=name, type=col_type) for name, col_type in test_case.warehouse_columns
    )

    result: PlanWarning | None = check_cursor_type_consistency(
        model_name=_MODEL_NAME,
        cursor_column=test_case.cursor_column,
        cursor_type=test_case.cursor_type,
        warehouse_columns=columns,
        sql_analysis_enabled=test_case.sql_analysis_enabled,
    )

    assert result is None
    assert not test_case.expected_warning
