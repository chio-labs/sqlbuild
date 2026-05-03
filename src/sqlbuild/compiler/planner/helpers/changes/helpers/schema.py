"""Schema change detection by column comparison."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.planner.models import SchemaFinding
from sqlbuild.compiler.planner.types import SchemaChangeKind


def detect_schema_changes(
    *,
    expected_columns: tuple[ColumnInfo, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
) -> tuple[SchemaFinding, ...]:
    """Compare expected columns against warehouse columns and return findings."""

    expected_map: dict[str, str] = {col.name: col.type for col in expected_columns}
    warehouse_map: dict[str, str] = {col.name: col.type for col in warehouse_columns}
    findings: list[SchemaFinding] = []

    col_name: str
    col_type: str
    for col_name, col_type in expected_map.items():
        if col_name not in warehouse_map:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_ADDED,
                    column_name=col_name,
                    expected_type=col_type,
                )
            )
        elif warehouse_map[col_name] != col_type:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                    column_name=col_name,
                    expected_type=col_type,
                    actual_type=warehouse_map[col_name],
                )
            )

    for col_name, col_type in warehouse_map.items():
        if col_name not in expected_map:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_REMOVED,
                    column_name=col_name,
                    actual_type=col_type,
                )
            )

    return tuple(findings)
