"""Staging relation creation for staged table promotion."""

from __future__ import annotations

from typing import Any

from sqlbuild._native import Fingerprint
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.run._helpers.execution.table_config import model_table_config
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
        create_intermediate_table(
            adapter=adapter,
            connection=connection,
            destination=staging_qualified,
            sql=resolved_sql,
            config=model_table_config(context.entry),
            statement_recorder=statement_recorder,
        )
        lifecycle.completed(metadata={"changed_count": 1})
    return None


def create_intermediate_table(
    *,
    adapter: BaseAdapter,
    connection: Any,
    destination: str,
    sql: str,
    config: dict[str, Any] | None,
    statement_recorder: StatementRecorder,
) -> None:
    """Create a table only SQLBuild writes, replacing one an interrupted run left behind."""

    if not adapter.create_table_as_replaces():
        adapter.drop_table(
            connection=connection, destination=destination, statement_recorder=statement_recorder
        )
    adapter.create_table_as(
        connection=connection,
        destination=destination,
        sql=sql,
        config=config,
        statement_recorder=statement_recorder,
    )
