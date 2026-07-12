"""Schema reconciliation helpers for source loader writes."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.adapter.shared.type_normalization import types_equal
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.spec.models.source import SourceEntry


def validate_and_evolve_existing_target(
    *,
    adapter: BaseAdapter,
    connection: Any,
    source_entry: SourceEntry,
    target: str,
    staging_columns: tuple[ColumnInfo, ...],
    statement_recorder: StatementRecorder,
) -> None:
    target_columns: tuple[ColumnInfo, ...] = adapter.describe_relation(
        connection=connection, relation=target
    )
    target_by_name: dict[str, ColumnInfo] = {
        column.name.lower(): column for column in target_columns
    }
    new_columns: list[ColumnInfo] = []
    staging_column: ColumnInfo
    for staging_column in staging_columns:
        target_column: ColumnInfo | None = target_by_name.get(staging_column.name.lower())
        if target_column is None:
            if source_entry.contract == "enforced":
                raise ExecutorInputError(
                    f"Source '{source_entry.name}' contract has extra columns: "
                    f"{staging_column.name}"
                )
            new_columns.append(staging_column)
            continue
        if types_equal(
            left=target_column.type,
            right=staging_column.type,
            dialect=adapter.sql_analysis_dialect_name,
        ):
            continue
        raise ExecutorInputError(
            f"Source '{source_entry.name}' column '{staging_column.name}' changed type from "
            f"{target_column.type} to {staging_column.type}"
        )
    if new_columns:
        adapter.add_columns(
            connection=connection,
            destination=target,
            columns=tuple(new_columns),
            statement_recorder=statement_recorder,
        )
