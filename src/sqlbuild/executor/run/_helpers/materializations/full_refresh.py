"""Shared build-aside full-refresh relation lifecycle."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.executor.run.models import FullRefreshRelations

_PREVIOUS_PREFIX: str = "__sqb_prev__"
_REBUILD_PREFIX: str = "__sqb_rebuild__"


def resolve_full_refresh_relations(
    *,
    adapter: BaseAdapter,
    database: str | None,
    schema: str | None,
    target_name: str,
) -> FullRefreshRelations:
    """Resolve identifier-fitted build-aside relation names."""

    identifier_limit: int = adapter.maximum_identifier_length()
    rebuild_name: str = _artifact_name(
        logical_name=target_name,
        fixed_prefix=_REBUILD_PREFIX,
        identifier_limit=identifier_limit,
    )
    previous_name: str = _artifact_name(
        logical_name=target_name,
        fixed_prefix=_PREVIOUS_PREFIX,
        identifier_limit=identifier_limit,
    )
    return FullRefreshRelations(
        target_name=target_name,
        target_qualified=_qualified(
            adapter=adapter, database=database, schema=schema, name=target_name
        ),
        rebuild_name=rebuild_name,
        rebuild_qualified=_qualified(
            adapter=adapter, database=database, schema=schema, name=rebuild_name
        ),
        previous_name=previous_name,
        previous_qualified=_qualified(
            adapter=adapter, database=database, schema=schema, name=previous_name
        ),
    )


def relation_exists(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str | None,
    name: str,
) -> bool:
    """Inspect whether one full-refresh relation exists."""

    return adapter.relation_exists(
        connection=connection, database=database, schema=schema, name=name
    )


def promote_full_refresh_rebuild(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relations: FullRefreshRelations,
    target_exists: bool,
    statement_recorder: StatementRecorder,
) -> None:
    """Promote a rebuild; dropping prev at the next swap is retention pruning only."""

    if not target_exists:
        adapter.rename(
            connection=connection,
            origin=relations.rebuild_qualified,
            destination=relations.target_qualified,
            statement_recorder=statement_recorder,
        )
        return
    adapter.drop(
        connection=connection,
        destination=relations.previous_qualified,
        if_exists=True,
        statement_recorder=statement_recorder,
    )
    if adapter.adapter_name == BuiltinAdapter.SNOWFLAKE:
        adapter.swap(
            connection=connection,
            left=relations.target_qualified,
            right=relations.rebuild_qualified,
            statement_recorder=statement_recorder,
        )
        adapter.rename(
            connection=connection,
            origin=relations.rebuild_qualified,
            destination=relations.previous_qualified,
            statement_recorder=statement_recorder,
        )
        return
    adapter.rename(
        connection=connection,
        origin=relations.target_qualified,
        destination=relations.previous_qualified,
        statement_recorder=statement_recorder,
    )
    adapter.rename(
        connection=connection,
        origin=relations.rebuild_qualified,
        destination=relations.target_qualified,
        statement_recorder=statement_recorder,
    )


def _artifact_name(*, logical_name: str, fixed_prefix: str, identifier_limit: int) -> str:
    available: int = identifier_limit - len(fixed_prefix)
    if len(logical_name) <= available:
        return fixed_prefix + logical_name
    digest: str = hashlib.sha256(logical_name.encode()).hexdigest()[:12]
    fitted: str = logical_name[: max(1, available - len(digest) - 1)]
    return f"{fixed_prefix}{fitted}_{digest}"


def _qualified(*, adapter: BaseAdapter, database: str | None, schema: str | None, name: str) -> str:
    return resolve_qualified_name_parts(
        adapter=adapter, database=database, schema=schema, name=name
    )
