"""Schema change detection by column comparison."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import InferredColumn
from sqlbuild.compiler.planner.models import SchemaFinding
from sqlbuild.compiler.planner.types import SchemaChangeKind, SchemaColumnSource


def detect_schema_changes(
    *,
    yml_columns: tuple[ColumnInfo, ...],
    inferred_columns: tuple[InferredColumn, ...] | None,
    warehouse_columns: tuple[ColumnInfo, ...],
    type_enforcement: bool,
) -> tuple[SchemaFinding, ...]:
    """Compare yml and inferred columns against warehouse columns and return findings."""

    warehouse_map: dict[str, str] = {col.name: col.type for col in warehouse_columns}
    findings: list[SchemaFinding] = []

    seen_names: set[str] = set()

    if type_enforcement:
        findings.extend(_compare_yml_columns(yml_columns=yml_columns, warehouse_map=warehouse_map))
        col: ColumnInfo
        for col in yml_columns:
            seen_names.add(col.name)

        if inferred_columns is not None:
            findings.extend(
                _compare_inferred_columns(
                    inferred_columns=inferred_columns,
                    warehouse_map=warehouse_map,
                    seen_names=seen_names,
                )
            )
            inferred_col: InferredColumn
            for inferred_col in inferred_columns:
                seen_names.add(inferred_col.name)
    else:
        if inferred_columns is not None:
            findings.extend(
                _compare_inferred_columns(
                    inferred_columns=inferred_columns,
                    warehouse_map=warehouse_map,
                    seen_names=seen_names,
                )
            )
            inferred_col_ne: InferredColumn
            for inferred_col_ne in inferred_columns:
                seen_names.add(inferred_col_ne.name)

        findings.extend(
            _compare_yml_columns_non_enforced(
                yml_columns=yml_columns,
                warehouse_map=warehouse_map,
                seen_names=seen_names,
            )
        )
        col_ne: ColumnInfo
        for col_ne in yml_columns:
            seen_names.add(col_ne.name)

    col_name: str
    col_type: str
    for col_name, col_type in warehouse_map.items():
        if col_name not in seen_names:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_REMOVED,
                    column_name=col_name,
                    source=SchemaColumnSource.YML if yml_columns else SchemaColumnSource.SQLGLOT,
                    actual_type=col_type,
                )
            )

    return tuple(findings)


def _compare_yml_columns(
    *,
    yml_columns: tuple[ColumnInfo, ...],
    warehouse_map: dict[str, str],
) -> list[SchemaFinding]:
    """Compare yml-declared columns against warehouse state."""

    findings: list[SchemaFinding] = []
    col: ColumnInfo
    for col in yml_columns:
        if col.name not in warehouse_map:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_ADDED,
                    column_name=col.name,
                    source=SchemaColumnSource.YML,
                    expected_type=col.type,
                )
            )
        elif warehouse_map[col.name] != col.type:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                    column_name=col.name,
                    source=SchemaColumnSource.YML,
                    expected_type=col.type,
                    actual_type=warehouse_map[col.name],
                )
            )
    return findings


def _compare_yml_columns_non_enforced(
    *,
    yml_columns: tuple[ColumnInfo, ...],
    warehouse_map: dict[str, str],
    seen_names: set[str],
) -> list[SchemaFinding]:
    """Compare yml columns against warehouse when type enforcement is off."""

    findings: list[SchemaFinding] = []
    col: ColumnInfo
    for col in yml_columns:
        if col.name in seen_names:
            continue
        if col.name not in warehouse_map:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_ADDED,
                    column_name=col.name,
                    source=SchemaColumnSource.YML,
                    expected_type=col.type,
                )
            )
        elif warehouse_map[col.name] != col.type:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                    column_name=col.name,
                    source=SchemaColumnSource.YML,
                    expected_type=col.type,
                    actual_type=warehouse_map[col.name],
                )
            )
    return findings


def _compare_inferred_columns(
    *,
    inferred_columns: tuple[InferredColumn, ...],
    warehouse_map: dict[str, str],
    seen_names: set[str],
) -> list[SchemaFinding]:
    """Compare sql_analysis-inferred columns against warehouse state, skipping yml-covered names."""

    findings: list[SchemaFinding] = []
    col: InferredColumn
    for col in inferred_columns:
        if col.name in seen_names:
            continue
        if col.name not in warehouse_map:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_ADDED,
                    column_name=col.name,
                    source=SchemaColumnSource.SQLGLOT,
                    expected_type=col.type,
                )
            )
        elif col.type is not None and warehouse_map[col.name] != col.type:
            findings.append(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                    column_name=col.name,
                    source=SchemaColumnSource.SQLGLOT,
                    expected_type=col.type,
                    actual_type=warehouse_map[col.name],
                )
            )
    return findings
