"""Build a compiled project with target defaults and adapter-aware validation."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.assemble_project import assemble_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.target_defaults import apply_target_defaults
from sqlbuild.compiler.pipeline.helpers.target_validation import validate_project_targets
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def build_compiled_project(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_environment: str | None = None,
    no_sql_validation: bool = False,
) -> CompiledProject:
    """Build one compiled project with adapter defaults and target validation applied."""

    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs,
        selected_environment=selected_environment,
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
