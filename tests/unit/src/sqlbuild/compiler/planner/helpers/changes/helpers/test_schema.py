from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import InferredColumn
from sqlbuild.compiler.planner.helpers.changes.helpers.schema import detect_schema_changes
from sqlbuild.compiler.planner.models import SchemaFinding
from sqlbuild.compiler.planner.types import SchemaChangeKind, SchemaColumnSource
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes.helpers._test_types import (
    DetectSchemaChangesTestCase,
)

DETECT_SCHEMA_CHANGES_TEST_CASES: list[DetectSchemaChangesTestCase] = [
    DetectSchemaChangesTestCase(
        description="detects no changes when yml columns match warehouse with enforcement",
        yml_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        inferred_columns=None,
        warehouse_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        type_enforcement=True,
        expected_findings=(),
    ),
    DetectSchemaChangesTestCase(
        description="detects added column from yml with enforcement",
        yml_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="status", type="VARCHAR"),
        ),
        inferred_columns=None,
        warehouse_columns=(ColumnInfo(name="id", type="INTEGER"),),
        type_enforcement=True,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_ADDED,
                column_name="status",
                source=SchemaColumnSource.YML,
                expected_type="VARCHAR",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="detects removed column against yml with enforcement",
        yml_columns=(ColumnInfo(name="id", type="INTEGER"),),
        inferred_columns=None,
        warehouse_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="old_col", type="BOOLEAN"),
        ),
        type_enforcement=True,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_REMOVED,
                column_name="old_col",
                source=SchemaColumnSource.YML,
                actual_type="BOOLEAN",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="detects type changed column from yml with enforcement",
        yml_columns=(ColumnInfo(name="id", type="BIGINT"),),
        inferred_columns=None,
        warehouse_columns=(ColumnInfo(name="id", type="INTEGER"),),
        type_enforcement=True,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                column_name="id",
                source=SchemaColumnSource.YML,
                expected_type="BIGINT",
                actual_type="INTEGER",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="detects added column from sqlglot when yml has no columns",
        yml_columns=(),
        inferred_columns=(
            InferredColumn(name="id", type=None),
            InferredColumn(name="new_col", type=None),
        ),
        warehouse_columns=(ColumnInfo(name="id", type="INTEGER"),),
        type_enforcement=False,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_ADDED,
                column_name="new_col",
                source=SchemaColumnSource.SQLGLOT,
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="detects type change from sqlglot explicit cast",
        yml_columns=(),
        inferred_columns=(InferredColumn(name="amount", type="DECIMAL(10, 2)"),),
        warehouse_columns=(ColumnInfo(name="amount", type="INTEGER"),),
        type_enforcement=False,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                column_name="amount",
                source=SchemaColumnSource.SQLGLOT,
                expected_type="DECIMAL(10, 2)",
                actual_type="INTEGER",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="skips type comparison for inferred column with no type",
        yml_columns=(),
        inferred_columns=(InferredColumn(name="amount", type=None),),
        warehouse_columns=(ColumnInfo(name="amount", type="INTEGER"),),
        type_enforcement=False,
        expected_findings=(),
    ),
    DetectSchemaChangesTestCase(
        description="enforced yml type wins over inferred type for same column",
        yml_columns=(ColumnInfo(name="amount", type="DECIMAL"),),
        inferred_columns=(InferredColumn(name="amount", type="FLOAT"),),
        warehouse_columns=(ColumnInfo(name="amount", type="INTEGER"),),
        type_enforcement=True,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                column_name="amount",
                source=SchemaColumnSource.YML,
                expected_type="DECIMAL",
                actual_type="INTEGER",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="non-enforced inferred type wins over yml type for same column",
        yml_columns=(ColumnInfo(name="amount", type="DECIMAL"),),
        inferred_columns=(InferredColumn(name="amount", type="FLOAT"),),
        warehouse_columns=(ColumnInfo(name="amount", type="INTEGER"),),
        type_enforcement=False,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                column_name="amount",
                source=SchemaColumnSource.SQLGLOT,
                expected_type="FLOAT",
                actual_type="INTEGER",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="non-enforced yml type used when inferred has no type for same column",
        yml_columns=(ColumnInfo(name="amount", type="DECIMAL"),),
        inferred_columns=(InferredColumn(name="amount", type=None),),
        warehouse_columns=(ColumnInfo(name="amount", type="INTEGER"),),
        type_enforcement=False,
        expected_findings=(),
    ),
    DetectSchemaChangesTestCase(
        description="non-enforced yml detects added column not covered by inferred",
        yml_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="extra", type="VARCHAR"),
        ),
        inferred_columns=(InferredColumn(name="id", type=None),),
        warehouse_columns=(ColumnInfo(name="id", type="INTEGER"),),
        type_enforcement=False,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_ADDED,
                column_name="extra",
                source=SchemaColumnSource.YML,
                expected_type="VARCHAR",
            ),
        ),
    ),
    DetectSchemaChangesTestCase(
        description="removed column uses sqlglot source when no yml columns exist",
        yml_columns=(),
        inferred_columns=(InferredColumn(name="id", type=None),),
        warehouse_columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="old_col", type="BOOLEAN"),
        ),
        type_enforcement=False,
        expected_findings=(
            SchemaFinding(
                kind=SchemaChangeKind.COLUMN_REMOVED,
                column_name="old_col",
                source=SchemaColumnSource.SQLGLOT,
                actual_type="BOOLEAN",
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
        yml_columns=test_case.yml_columns,
        inferred_columns=test_case.inferred_columns,
        warehouse_columns=test_case.warehouse_columns,
        type_enforcement=test_case.type_enforcement,
    )

    assert result == test_case.expected_findings
