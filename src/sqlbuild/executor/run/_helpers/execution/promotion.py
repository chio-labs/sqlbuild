"""Relation promotion helpers for run execution lifecycles."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import PromotionStrategy
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run._helpers.execution.permanent_promotion import (
    permanent_operation_identity,
    promote_permanent_relation,
)
from sqlbuild.executor.run.models import (
    ModelMaterializationContext,
    TableLifecycleState,
    TableTargets,
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
) -> None:
    """Promote an already-created relation into its final destination."""

    existing: bool = adapter.relation_exists(
        connection=connection,
        database=destination_database,
        schema=destination_schema,
        name=destination_name,
    )
    promotion_strategy: PromotionStrategy = adapter.default_promotion_strategy()
    if existing and promotion_strategy == PromotionStrategy.ATOMIC_SWAP:
        adapter.swap(
            connection=connection,
            left=destination_relation,
            right=origin_relation,
            statement_recorder=statement_recorder,
        )
        adapter.drop(
            connection=connection,
            destination=origin_relation,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
        return
    if existing and promotion_strategy == PromotionStrategy.ATOMIC_REPLACE:
        adapter.replace_table_from_relation(
            connection=connection,
            destination=destination_relation,
            origin=origin_relation,
            statement_recorder=statement_recorder,
        )
        adapter.drop(
            connection=connection,
            destination=origin_relation,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
        return
    if existing:
        raise ExecutorInputError(f"Unsupported promotion strategy: {promotion_strategy}")
    adapter.rename(
        connection=connection,
        origin=origin_relation,
        destination=destination_relation,
        statement_recorder=statement_recorder,
    )


def promote_staged_table(
    *, context: ModelMaterializationContext, targets: TableTargets, state: TableLifecycleState
) -> None:
    """Dispatch ordinary staged promotion according to the requested physical table kind."""

    entry: ModelPlanEntry = context.entry
    if entry.permanent_table:
        _ = promote_permanent_relation(
            adapter=context.adapter,
            connection=context.connection,
            staging_relation=targets.staging_qualified,
            staging_name=targets.staging_table,
            destination_relation=targets.target_qualified,
            destination_database=targets.target_database,
            destination_schema=targets.target_schema,
            destination_name=targets.target_table,
            operation_identity=permanent_operation_identity(
                entry=entry,
                run_id=context.run_id,
            ),
            statement_recorder=state.statement_recorder,
        )
        return
    _ = promote_relation_to_destination(
        adapter=context.adapter,
        connection=context.connection,
        origin_relation=targets.staging_qualified,
        destination_relation=targets.target_qualified,
        destination_database=targets.target_database,
        destination_schema=targets.target_schema,
        destination_name=targets.target_table,
        statement_recorder=state.statement_recorder,
    )
