"""Direct node result store factory."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.executor.node_results.classes.direct_store import DirectNodeResultStore


def build_direct_node_result_store(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str | None,
) -> DirectNodeResultStore:
    """Build a direct-mode runtime node result store."""

    return DirectNodeResultStore(
        adapter=adapter,
        connection=connection,
        database=database,
        schema=schema,
    )
