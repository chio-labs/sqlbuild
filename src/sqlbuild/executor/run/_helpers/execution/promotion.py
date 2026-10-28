"""Relation promotion helpers for run execution lifecycles."""

from __future__ import annotations

from typing import Any

from sqlbuild._native import OPERATION_STRATEGIES
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import PromotionStrategy, RelationType
from sqlbuild.adapter.relations.main.cached_relation_exists import cached_relation_exists
from sqlbuild.adapter.relations.main.cached_relation_type import cached_relation_type
from sqlbuild.adapter.relations.main.invalidate_cached_relations import invalidate_cached_relations
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run.models import BoundViewGuard
from sqlbuild.runtime.observability.classes.operation_lifecycle import (
    OperationAttributes,
    OperationLifecycle,
)
from sqlbuild.runtime.observability.constants import RENAME_OPERATION_STRATEGY
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
        strategy: str = _promotion_strategy(adapter=adapter, existing=existing)
        terminal_attributes: OperationAttributes | None = (
            OperationAttributes(strategy=strategy) if strategy in OPERATION_STRATEGIES else None
        )
        relations: tuple[str, str] = (origin_relation, destination_relation)
        try:
            _promote(
                adapter=adapter,
                connection=connection,
                strategy=strategy,
                relations=relations,
                guard=guard,
                statement_recorder=statement_recorder,
            )
        except Exception as error:
            if isinstance(error, ExecutorInputError):
                lifecycle.failed(error=error, attributes=terminal_attributes)
                raise
            live_existing: bool = _live_existence(
                adapter=adapter,
                connection=connection,
                destination=(destination_database, destination_schema, destination_name),
                destination_relation=destination_relation,
            )
            if live_existing != existing:
                strategy = _promotion_strategy(adapter=adapter, existing=live_existing)
                terminal_attributes = (
                    OperationAttributes(strategy=strategy)
                    if strategy in OPERATION_STRATEGIES
                    else None
                )
                try:
                    _promote(
                        adapter=adapter,
                        connection=connection,
                        strategy=strategy,
                        relations=relations,
                        guard=guard,
                        statement_recorder=statement_recorder,
                    )
                except Exception as retry_error:
                    lifecycle.failed(error=retry_error, attributes=terminal_attributes)
                    raise
                lifecycle.completed(metadata={"changed_count": 1}, attributes=terminal_attributes)
                return
            if not existing or not _dropped_replaced_view(
                adapter=adapter,
                connection=connection,
                destination=(destination_database, destination_schema, destination_name),
                destination_relation=destination_relation,
                statement_recorder=statement_recorder,
            ):
                lifecycle.failed(error=error, attributes=terminal_attributes)
                raise
            try:
                adapter.rename(
                    connection=connection,
                    origin=origin_relation,
                    destination=destination_relation,
                    statement_recorder=statement_recorder,
                )
            except Exception as rename_error:
                lifecycle.failed(error=rename_error, attributes=terminal_attributes)
                raise
        lifecycle.completed(metadata={"changed_count": 1}, attributes=terminal_attributes)


def _promotion_strategy(*, adapter: BaseAdapter, existing: bool) -> str:
    """Rename into an absent destination; otherwise the adapter's replacement strategy."""

    return RENAME_OPERATION_STRATEGY if not existing else str(adapter.default_promotion_strategy())


def _promote(
    *,
    adapter: BaseAdapter,
    connection: Any,
    strategy: str,
    relations: tuple[str, str],
    guard: BoundViewGuard,
    statement_recorder: StatementRecorder,
) -> None:
    """Move the staged ``origin`` into ``destination`` with one promotion strategy."""

    origin_relation, destination_relation = relations
    if strategy == PromotionStrategy.ATOMIC_SWAP:
        with guard.transaction():
            adapter.swap(
                connection=connection,
                left=destination_relation,
                right=origin_relation,
                statement_recorder=statement_recorder,
            )
            _ = guard.rebind()
            adapter.drop_table(
                connection=connection,
                destination=origin_relation,
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
            adapter.drop_table(
                connection=connection,
                destination=origin_relation,
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


def _live_existence(
    *,
    adapter: BaseAdapter,
    connection: Any,
    destination: tuple[str | None, str | None, str],
    destination_relation: str,
) -> bool:
    """Read the destination's existence again, past what this build remembered of it."""

    invalidate_cached_relations(adapter=adapter, qualified_names=(destination_relation,))
    database, schema, name = destination
    return cached_relation_exists(
        adapter=adapter, connection=connection, database=database, schema=schema, name=name
    )


def _dropped_replaced_view(
    *,
    adapter: BaseAdapter,
    connection: Any,
    destination: tuple[str | None, str | None, str],
    destination_relation: str,
    statement_recorder: StatementRecorder,
) -> bool:
    """Drop the live destination when it is a view a table cannot replace; whether it was one."""

    database, schema, name = destination
    existing: RelationType | None = cached_relation_type(
        adapter=adapter, connection=connection, database=database, schema=schema, name=name
    )
    if existing != RelationType.VIEW:
        return False
    adapter.drop_view(
        connection=connection,
        destination=destination_relation,
        if_exists=True,
        statement_recorder=statement_recorder,
    )
    return True
