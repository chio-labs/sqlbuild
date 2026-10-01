"""Relation promotion helpers for run execution lifecycles."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import PromotionStrategy
from sqlbuild.adapter.relations.main.cached_relation_exists import cached_relation_exists
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run.models import BoundViewGuard
from sqlbuild.runtime.observability.classes.operation_lifecycle import (
    OperationAttributes,
    OperationLifecycle,
)
from sqlbuild.runtime.observability.constants import (
    OPERATION_STRATEGIES,
    RENAME_OPERATION_STRATEGY,
)
from sqlbuild.runtime.observability.main.canonicalize_operation_adapter import (
    canonicalize_operation_adapter,
)


def promote_relation_to_destination(
    *,
    adapter: BaseAdapter,
    connection: Any,
    origin_relation: str,
    destination_relation: str,
    destination_database: str | None,
    destination_schema: str | None,
    destination_name: str,
    statement_recorder: StatementRecorder,
    bound_views: BoundViewGuard | None = None,
) -> None:
    """Promote an already-created relation into its final destination."""

    guard: BoundViewGuard = bound_views or BoundViewGuard()

    with OperationLifecycle(
        operation_kind="warehouse",
        operation_name="relation_promotion",
        attributes=OperationAttributes(
            phase="promote",
            adapter=canonicalize_operation_adapter(adapter.adapter_name),
            target_kind="relation",
        ),
    ) as lifecycle:
        existing: bool = cached_relation_exists(
            adapter=adapter,
            connection=connection,
            database=destination_database,
            schema=destination_schema,
            name=destination_name,
        )
        strategy: str = (
            RENAME_OPERATION_STRATEGY if not existing else str(adapter.default_promotion_strategy())
        )
        terminal_attributes: OperationAttributes | None = (
            OperationAttributes(strategy=strategy) if strategy in OPERATION_STRATEGIES else None
        )
        try:
            if strategy == PromotionStrategy.ATOMIC_SWAP:
                with guard.transaction():
                    adapter.swap(
                        connection=connection,
                        left=destination_relation,
                        right=origin_relation,
                        statement_recorder=statement_recorder,
                    )
                    _ = guard.rebind()
                    adapter.drop(
                        connection=connection,
                        destination=origin_relation,
                        if_exists=True,
                        statement_recorder=statement_recorder,
                    )
            elif strategy == PromotionStrategy.ATOMIC_REPLACE:
                with guard.transaction():
                    adapter.replace_table_from_relation(
                        connection=connection,
                        destination=destination_relation,
                        origin=origin_relation,
                        statement_recorder=statement_recorder,
                    )
                    _ = guard.rebind()
                    adapter.drop(
                        connection=connection,
                        destination=origin_relation,
                        if_exists=True,
                        statement_recorder=statement_recorder,
                    )
            elif strategy == RENAME_OPERATION_STRATEGY:
                adapter.rename(
                    connection=connection,
                    origin=origin_relation,
                    destination=destination_relation,
                    statement_recorder=statement_recorder,
                )
            else:
                raise ExecutorInputError(f"Unsupported promotion strategy: {strategy}")
        except Exception as error:
            lifecycle.failed(error=error, attributes=terminal_attributes)
            raise
        lifecycle.completed(metadata={"changed_count": 1}, attributes=terminal_attributes)
