"""Relation promotion helpers for run execution lifecycles."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapter.shared.types import PromotionStrategy
from sqlbuild.executor.exceptions import ExecutorInputError


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
