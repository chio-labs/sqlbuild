"""Clone pipeline assembly helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.assemble_project import assemble_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.target_defaults import apply_target_defaults
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.compiler.planner.main.clone import run_clone_planning


def prepare_clone_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    from_environment: str,
    to_environment: str,
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    target_connection: Any,
) -> ClonePipelineResult:
    source_project: CompiledProject = _compile_project_for_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        environment_name=from_environment,
        no_sql_validation=no_sql_validation,
    )
    target_project: CompiledProject = _compile_project_for_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        environment_name=to_environment,
        no_sql_validation=no_sql_validation,
    )
    (
        clone_plan,
        target_model_entries,
        target_seed_entries,
        source_model_entries,
        source_seed_entries,
    ) = run_clone_planning(
        project=target_project,
        select=select,
        exclude=exclude,
        adapter=adapter,
        connection=target_connection,
        source_project=source_project,
    )
    return ClonePipelineResult(
        source_project=source_project,
        target_project=target_project,
        clone_plan=clone_plan,
        target_model_entries=target_model_entries,
        target_seed_entries=target_seed_entries,
        source_model_entries=source_model_entries,
        source_seed_entries=source_seed_entries,
    )


def _compile_project_for_environment(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    environment_name: str,
    no_sql_validation: bool,
) -> CompiledProject:
    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs,
        selected_environment=environment_name,
        no_sql_validation=no_sql_validation,
    )
    return apply_target_defaults(
        assemble_project(compile_inputs),
        default_schema=adapter.default_schema(),
        default_database=adapter.default_database(),
    )
