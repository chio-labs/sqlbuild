"""Full compile-and-plan pipeline producing CLI artifacts."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.assemble_project import assemble_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs, LoadedMacro
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.manifest.main import build_manifest
from sqlbuild.compiler.pipeline.helpers.target_defaults import apply_target_defaults
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.main import build_execution_plan
from sqlbuild.compiler.planner.models import PlanOutput


def run_compile_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    no_sql_validation: bool = False,
) -> CompilePipelineResult:
    """Run compile inputs, assembly, planning, and manifest generation."""

    connection: Any = adapter.connect(dict(discovered_inputs.project_config.connection))
    try:
        return _build_result(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            connection=connection,
            no_sql_validation=no_sql_validation,
        )
    finally:
        adapter.close(connection)


def _build_result(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection: Any,
    no_sql_validation: bool,
) -> CompilePipelineResult:
    """Build the complete pipeline result with an open connection."""

    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs,
        no_sql_validation=no_sql_validation,
    )
    project: CompiledProject = apply_target_defaults(
        assemble_project(compile_inputs),
        default_schema=adapter.default_schema(),
        default_database=adapter.default_database(),
    )
    plan_output: PlanOutput = build_execution_plan(
        project=project,
        adapter=adapter,
        connection=connection,
    )
    loaded_macros: dict[str, LoadedMacro] = load_macros(discovered_inputs.macro_files)
    manifest: dict[str, object] = build_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros=loaded_macros,
        project_name=discovered_inputs.project_config.name,
        adapter_type=discovered_inputs.project_config.adapter,
        upstream_deps=plan_output.upstream_deps,
        downstream_deps=plan_output.downstream_deps,
    )

    return CompilePipelineResult(
        project=project,
        plan_output=plan_output,
        manifest=manifest,
    )
