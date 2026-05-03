"""Public diff pipeline entrypoints."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.diff import (
    compile_project_for_diff_environment,
    resolve_diff_model_names,
)


def run_diff_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    from_environment: str,
    to_environment: str,
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[CompiledProject, CompiledProject, tuple[str, ...]]:
    """Compile both environments and resolve selected diffable model names."""

    left_project: CompiledProject = compile_project_for_diff_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        environment_name=from_environment,
        no_sql_validation=no_sql_validation,
    )
    right_project: CompiledProject = compile_project_for_diff_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        environment_name=to_environment,
        no_sql_validation=no_sql_validation,
    )
    selected_names: tuple[str, ...] = resolve_diff_model_names(
        project=right_project,
        select=select,
        exclude=exclude,
    )
    return left_project, right_project, selected_names
