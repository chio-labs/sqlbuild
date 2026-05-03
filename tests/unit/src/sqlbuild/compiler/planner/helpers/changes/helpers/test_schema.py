from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.planner.helpers.changes.helpers.schema import detect_schema_changes
from sqlbuild.compiler.planner.models import SchemaFinding
from sqlbuild.compiler.planner.types import SchemaChangeKind
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes.helpers._test_types import (
    DetectSchemaChangesTestCase,
)

DETECT_SCHEMA_CHANGES_TEST_CASES: list[DetectSchemaChangesTestCase] = [
    DetectSchemaChangesTestCase(
        description="detects no changes when columns match",
        expected_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        warehouse_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        expected_findings=(),
    ),
    DetectSchemaChangesTestCase(
        description="detects added column",
        expected_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="status", type="VARCHAR"),
        ),
        warehouse_columns=(ColumnInfo(name="id", type="INTEGER"),),
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_ADDED,
                column_name="status",
                expected_type="VARCHAR",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="detects removed column",
        expected_columns=(ColumnInfo(name="id", type="INTEGER"),),
        warehouse_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="old_col", type="BOOLEAN"),
        ),
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_REMOVED,
                column_name="old_col",
                actual_type="BOOLEAN",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="detects type changed column",
        expected_columns=(ColumnInfo(name="id", type="BIGINT"),),
        warehouse_columns=(ColumnInfo(name="id", type="INTEGER"),),
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                column_name="id",
                expected_type="BIGINT",
                actual_type="INTEGER",
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DETECT_SCHEMA_CHANGES_TEST_CASES,
    ids=[case.description for case in DETECT_SCHEMA_CHANGES_TEST_CASES],
)
def test_given_columns_when_detecting_schema_changes_then_returns_expected_findings(
    test_case: DetectSchemaChangesTestCase,
) -> None:
    result: tuple[SchemaFinding, ...] = detect_schema_changes(
        expected_columns=test_case.expected_columns,
        warehouse_columns=test_case.warehouse_columns,
    )

    assert result == test_case.expected_findings
