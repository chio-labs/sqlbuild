"""Build dbt node source watermark context."""

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkExecutionContext
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from sqlbuild.integrations.dbt.helpers.runtime.node_source_watermarks import (
    build_dbt_node_source_watermark_context as _build,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph


def build_dbt_node_source_watermark_context(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    source_records: tuple[SourceFreshnessRecord, ...],
    adapter: BaseAdapter,
    connection: Any,
    state_database: str | None,
    state_schema: str | None,
) -> NodeSourceWatermarkExecutionContext | None:
    """Build watermark context for one dbt execution."""

    return _build(
        manifest=manifest,
        graph=graph,
        source_records=source_records,
        adapter=adapter,
        connection=connection,
        state_database=state_database,
        state_schema=state_schema,
    )
