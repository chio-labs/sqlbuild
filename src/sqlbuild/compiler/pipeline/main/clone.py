"""Public clone pipeline entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.clone import prepare_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult


def run_clone_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    from_environment: str,
    to_environment: str,
    no_sql_validation: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    target_connection: Any,
) -> ClonePipelineResult:
    return prepare_clone_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        from_environment=from_environment,
        to_environment=to_environment,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
        target_connection=target_connection,
    )
