"""Public clone pipeline entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.clone import prepare_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.shared.types import ExternalSqlReferenceResolver


def run_clone_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    from_target: str,
    to_target: str,
    no_sql_validation: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    target_connection: Any,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> ClonePipelineResult:
    return prepare_clone_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        from_target=from_target,
        to_target=to_target,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
        cli_vars=cli_vars,
        target_connection=target_connection,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
