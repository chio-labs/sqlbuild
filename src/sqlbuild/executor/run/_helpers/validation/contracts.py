"""Runtime validation for enforced model contracts."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.exceptions import ExecutorInputError
from sqlbuild.executor.run.constants import (
    RUNTIME_CONTRACT_EXTRA_COLUMN_CODE,
    RUNTIME_CONTRACT_MISSING_COLUMN_CODE,
    RUNTIME_CONTRACT_MISSING_DECLARATIONS_CODE,
    RUNTIME_CONTRACT_TYPE_MISMATCH_CODE,
)


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
            f"model '{entry.name}' has contract enforced but declares no columns",
            code=RUNTIME_CONTRACT_MISSING_DECLARATIONS_CODE,
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
            f"model '{entry.name}' runtime contract missing columns: {', '.join(missing_names)}",
            code=RUNTIME_CONTRACT_MISSING_COLUMN_CODE,
        )

    extra_names: tuple[str, ...] = tuple(
        column.name for column in actual_columns if column.name.lower() not in declared_by_name
    )
    if extra_names:
        raise ExecutorInputError(
            f"model '{entry.name}' runtime contract has extra columns: {', '.join(extra_names)}",
            code=RUNTIME_CONTRACT_EXTRA_COLUMN_CODE,
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
            f"has type {actual_column.type} but contract declares {declared_column.type}",
            code=RUNTIME_CONTRACT_TYPE_MISMATCH_CODE,
        )
