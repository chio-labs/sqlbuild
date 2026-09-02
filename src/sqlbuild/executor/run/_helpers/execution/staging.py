"""Staging relation creation for staged table promotion."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.executor.run.models import ModelMaterializationContext
from sqlbuild.runtime.observability.classes.operation_lifecycle import (
    OperationAttributes,
    OperationLifecycle,
)
from sqlbuild.runtime.observability.main.canonicalize_operation_adapter import (
    canonicalize_operation_adapter,
)


def create_staging_relation(
    *,
    context: ModelMaterializationContext,
    staging_qualified: str,
    resolved_sql: str,
    statement_recorder: StatementRecorder,
) -> Fingerprint | None:
    """Create the staging relation via CTAS."""

    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    with OperationLifecycle(
        operation_kind="warehouse",
        operation_name="staging_creation",
        attributes=OperationAttributes(
            phase="create",
            adapter=canonicalize_operation_adapter(adapter.adapter_name),
            target_kind="staging_relation",
        ),
    ) as lifecycle:
        adapter.drop(
            connection=connection,
            destination=staging_qualified,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
        adapter.create_table_as(
            connection=connection,
            destination=staging_qualified,
            sql=resolved_sql,
            config={"table_type": context.entry.table_type},
            statement_recorder=statement_recorder,
        )
        lifecycle.completed(metadata={"changed_count": 1})
    return None
