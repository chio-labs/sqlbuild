"""Compile a project without building an execution plan."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.assemble_project import assemble_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.target_defaults import apply_target_defaults
from sqlbuild.compiler.pipeline.helpers.target_validation import validate_project_targets
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def compile_project(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    no_sql_validation: bool = False,
) -> CompiledProject:
    """Compile discovered inputs into a target-defaulted project view."""

    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs,
        no_sql_validation=no_sql_validation,
    )
    project: CompiledProject = apply_target_defaults(
        assemble_project(compile_inputs),
        default_schema=adapter.default_schema(),
        default_database=adapter.default_database(),
    )
    validate_project_targets(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project=project,
    )
    return project
