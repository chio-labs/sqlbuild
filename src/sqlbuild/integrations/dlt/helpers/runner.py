"""In-process runner helpers for dlt."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.integrations.dlt.exceptions import DltIntegrationError
from sqlbuild.integrations.dlt.helpers.config import resolve_dlt_config
from sqlbuild.integrations.dlt.helpers.destination import build_dlt_destination
from sqlbuild.integrations.dlt.helpers.progress import SqlbuildDltProgressCollector
from sqlbuild.integrations.dlt.helpers.source import build_dlt_source
from sqlbuild.integrations.dlt.models import DltDestinationConfig, DltSourceConfig


def run_dlt_source(*, config: DltSourceConfig, ctx: LoaderContext) -> None:
    """Run one declarative dlt resource into the SQLBuild target dataset."""

    try:
        import dlt
    except ImportError as error:
        raise DltIntegrationError(
            "This source uses dlt, but dlt is not installed. Install it with: "
            "pip install 'sqlbuild[dlt]'"
        ) from error

    resolved: DltSourceConfig = resolve_dlt_config(
        config=config,
        vars=ctx.vars,
        environment=ctx.target,
        run_id=ctx.run_id,
    )
    destination: DltDestinationConfig = build_dlt_destination(
        adapter_name=ctx.adapter.adapter_name,
        connection_config=ctx.connection_config,
        dataset_name=resolved.resource.schema,
    )
    dlt_source: Any = build_dlt_source(resolved)
    pipelines_dir: Path = ctx.runtime_dir / "dlt"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    progress_collector: SqlbuildDltProgressCollector = SqlbuildDltProgressCollector(
        on_progress=ctx.progress
    )
    pipeline: Any = dlt.pipeline(
        pipeline_name=_pipeline_name(config=resolved, target=ctx.target),
        pipelines_dir=str(pipelines_dir),
        destination=destination.destination,
        dataset_name=cast(str, destination.dataset_name),
        progress=cast(Any, progress_collector),
    )
    pipeline.drop()
    load_info: Any = pipeline.run(
        dlt_source,
        destination=destination.destination,
        dataset_name=cast(str, destination.dataset_name),
        table_name=resolved.resource.name,
        write_disposition=cast(Any, resolved.resource.write_disposition),
        primary_key=cast(Any, resolved.resource.primary_key),
        refresh=cast(Any, "drop_resources" if ctx.is_reload else None),
    )
    load_info.raise_on_failed_jobs()
    progress_summary: str = progress_collector.format_summary()
    if progress_summary:
        ctx.log(progress_summary)
    ctx.log(str(load_info))
    return None


def _pipeline_name(*, config: DltSourceConfig, target: str | None) -> str:
    target_part: str = target or "default"
    return (
        f"sqlbuild_{target_part}_{config.source_type}_{config.group_index}_{config.resource.name}"
    )
