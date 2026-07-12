"""Public diff pipeline entrypoints."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.diff import (
    compile_project_for_diff_environment,
    resolve_diff_model_names,
)
from sqlbuild.shared.types import ExternalSqlReferenceResolver


def run_diff_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    from_target: str,
    to_target: str,
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> tuple[CompiledProject, CompiledProject, tuple[str, ...]]:
    """Compile both environments and resolve selected diffable model names."""

    left_project: CompiledProject = compile_project_for_diff_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        target_name=from_target,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    right_project: CompiledProject = compile_project_for_diff_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        target_name=to_target,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    selected_names: tuple[str, ...] = resolve_diff_model_names(
        project=right_project,
        select=select,
        exclude=exclude,
    )
    return left_project, right_project, selected_names
