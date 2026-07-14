"""Record a dbt node source watermark."""

from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkExecutionContext
from sqlbuild.integrations.dbt.helpers.runtime.node_source_watermarks import (
    record_dbt_successful_node_source_watermark as _record,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult


def record_dbt_successful_node_source_watermark(
    *,
    context: NodeSourceWatermarkExecutionContext | None,
    result: DbtNodeExecutionResult,
    manifest: DbtManifestIndex,
    run_id: str,
    node_version_hash: str | None,
) -> None:
    """Buffer a watermark for one successful dbt model."""

    _ = _record(
        context=context,
        result=result,
        manifest=manifest,
        run_id=run_id,
        node_version_hash=node_version_hash,
    )
