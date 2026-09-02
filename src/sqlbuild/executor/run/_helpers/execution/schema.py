"""Canonical runtime schema inspection boundary."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.runtime.observability.classes.operation_lifecycle import (
    OperationAttributes,
    OperationLifecycle,
)
from sqlbuild.runtime.observability.main.canonicalize_operation_adapter import (
    canonicalize_operation_adapter,
)


def inspect_runtime_relation_schema(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str | None,
    name: str,
) -> tuple[ColumnInfo, ...]:
    """Inspect one runtime relation schema through a timed canonical operation."""

    with OperationLifecycle(
        operation_kind="warehouse",
        operation_name="runtime_schema_inspection",
        attributes=OperationAttributes(
            phase="inspect",
            adapter=canonicalize_operation_adapter(adapter.adapter_name),
            target_kind="relation",
        ),
    ) as lifecycle:
        columns: tuple[ColumnInfo, ...] = adapter.get_columns(
            connection=connection, database=database, schema=schema, name=name
        )
        lifecycle.completed(metadata={"item_count": len(columns)})
        return columns
