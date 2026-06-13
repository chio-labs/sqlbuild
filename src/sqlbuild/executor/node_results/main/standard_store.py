"""Standard node result store factory."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.executor.node_results.classes.standard_store import StandardNodeResultStore


def build_standard_node_result_store(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str | None,
) -> StandardNodeResultStore:
    """Build a standard-mode runtime node result store."""

    return StandardNodeResultStore(
        adapter=adapter,
        connection=connection,
        database=database,
        schema=schema,
    )
