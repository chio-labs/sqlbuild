"""Write dbt node source watermarks."""

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkExecutionContext
from sqlbuild.integrations.dbt._helpers.runtime.node_source_watermarks import (
    write_dbt_node_source_watermark_records as _write,
)


def write_dbt_node_source_watermark_records(
    *,
    context: NodeSourceWatermarkExecutionContext | None,
    adapter: BaseAdapter,
    connection: Any,
    state_database: str | None,
    state_schema: str | None,
) -> None:
    """Write buffered dbt node source watermark records."""

    _ = _write(
        context=context,
        adapter=adapter,
        connection=connection,
        state_database=state_database,
        state_schema=state_schema,
    )
