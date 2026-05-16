"""Runtime validation for enforced model contracts."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.adapter.shared.type_normalization import types_equal
from sqlbuild.adapter.shared.types import TypeDialect
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.shared.exceptions import ExecutorInputError


def validate_runtime_contract(
    *,
    entry: ModelPlanEntry,
    actual_columns: tuple[ColumnInfo, ...],
    dialect: TypeDialect | str | None = None,
) -> None:
    """Validate a staged relation's actual columns against an enforced contract."""

    if not entry.contract_enforced:
        return
    if not entry.contract_columns:
        raise ExecutorInputError(
            f"model '{entry.name}' has contract enforced but declares no columns"
        )

    declared_by_name: dict[str, ColumnInfo] = {
        column.name.lower(): column for column in entry.contract_columns
    }
    actual_by_name: dict[str, ColumnInfo] = {
        column.name.lower(): column for column in actual_columns
    }

    missing_names: tuple[str, ...] = tuple(
        column.name
        for column in entry.contract_columns
        if column.name.lower() not in actual_by_name
    )
    if missing_names:
        raise ExecutorInputError(
            f"model '{entry.name}' runtime contract missing columns: {', '.join(missing_names)}"
        )

    extra_names: tuple[str, ...] = tuple(
        column.name for column in actual_columns if column.name.lower() not in declared_by_name
    )
    if extra_names:
        raise ExecutorInputError(
            f"model '{entry.name}' runtime contract has extra columns: {', '.join(extra_names)}"
        )

    actual_column: ColumnInfo
    for actual_column in actual_columns:
        declared_column: ColumnInfo = declared_by_name[actual_column.name.lower()]
        if not declared_column.type or not actual_column.type:
            continue
        if types_equal(left=actual_column.type, right=declared_column.type, dialect=dialect):
            continue
        raise ExecutorInputError(
            f"model '{entry.name}' runtime contract column '{declared_column.name}' "
            f"has type {actual_column.type} but contract declares {declared_column.type}"
        )
