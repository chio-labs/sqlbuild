"""Clone pipeline entrypoint with typed compilation options."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline._helpers.clone import prepare_clone_pipeline
from sqlbuild.compiler.pipeline.models import (
    ClonePipelineConnection,
    ClonePipelineOptions,
    ClonePipelineResult,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver


def run_clone_pipeline_with_options(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str,
    destination_connection: ClonePipelineConnection,
    options: ClonePipelineOptions,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> ClonePipelineResult:
    """Run a clone pipeline with explicit compilation controls."""

    return prepare_clone_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        origin_target_name=origin_target_name,
        destination_target_name=destination_target_name,
        destination_connection=destination_connection,
        options=options,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
