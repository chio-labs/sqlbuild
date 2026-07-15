"""Clone pipeline assembly helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.compiler.planner.main.clone.clone import run_clone_planning
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver


def prepare_clone_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str,
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    cli_vars: dict[str, object] | None,
    destination_connection: Any,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> ClonePipelineResult:
    origin_project: CompiledProject = _compile_project_for_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        target_name=origin_target_name,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    destination_project: CompiledProject = _compile_project_for_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        target_name=destination_target_name,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    (
        clone_plan,
        destination_model_entries,
        destination_seed_entries,
        origin_model_entries,
        origin_seed_entries,
    ) = run_clone_planning(
        project=destination_project,
        select=select,
        exclude=exclude,
        adapter=adapter,
        connection=destination_connection,
        origin_project=origin_project,
    )
    return ClonePipelineResult(
        origin_project=origin_project,
        destination_project=destination_project,
        clone_plan=clone_plan,
        destination_model_entries=destination_model_entries,
        destination_seed_entries=destination_seed_entries,
        origin_model_entries=origin_model_entries,
        origin_seed_entries=origin_seed_entries,
    )


def _compile_project_for_environment(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    target_name: str,
    no_sql_validation: bool,
    cli_vars: dict[str, object] | None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> CompiledProject:
    return build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=target_name,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
