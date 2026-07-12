"""Public clone pipeline entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.clone import prepare_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.shared.types import ExternalSqlReferenceResolver


def run_clone_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str,
    no_sql_validation: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    destination_connection: Any,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> ClonePipelineResult:
    return prepare_clone_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        origin_target_name=origin_target_name,
        destination_target_name=destination_target_name,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
        cli_vars=cli_vars,
        destination_connection=destination_connection,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
