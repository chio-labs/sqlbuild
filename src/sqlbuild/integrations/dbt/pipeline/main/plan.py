"""Runtime planning pipeline for `sqb dbt plan`."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredDbtManifestFile, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.integrations.dbt.helpers.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.plan_orchestration import plan_dbt_interop_command
from sqlbuild.integrations.dbt.helpers.plan_runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandResult,
    DbtInteropPlan,
    DbtInteropRoutedArgs,
    DbtManifestIndex,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def plan_dbt_interop_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    dbt_runner: DbtRunner | None = None,
    dbt_executable: str = "dbt",
    sqlbuild_executable: str = "sqb",
    no_sql_validation: bool = False,
) -> DbtInteropPlan:
    """Build a dbt interop plan from real project files and dbt artifacts."""

    routed: DbtInteropRoutedArgs = route_dbt_interop_args(
        command=DbtInteropCommand.PLAN,
        args=args,
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=routed.dbt_args,
    )
    runner: DbtRunner = dbt_runner or DbtRunner(dbt_executable=dbt_executable)
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise ValueError(compile_result.stderr or compile_result.stdout or "dbt compile failed")
    manifest_path: Path = resolve_dbt_manifest_path(options=dbt_options)
    manifest: DbtManifestIndex = load_dbt_manifest_index(manifest_path=manifest_path)
    discovered_with_manifest: DiscoveredProjectInputs = replace(
        discovered_inputs,
        dbt_manifest_file=DiscoveredDbtManifestFile(
            file_path=manifest_path,
            relative_path=Path("manifest.json"),
            contents=manifest_path.read_text(encoding="utf-8"),
        ),
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(adapter_name, project_dir=project_dir)
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_with_manifest,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    return plan_dbt_interop_command(
        command=DbtInteropCommand.PLAN,
        project=project,
        manifest=manifest,
        graph=graph,
        dbt_runner=runner,
        dbt_options=dbt_options,
        select=routed.select,
        exclude=routed.exclude,
        dbt_command_args=routed.dbt_args,
        sqlbuild_command_args=routed.sqlbuild_args,
        dbt_executable=dbt_executable,
        sqlbuild_executable=sqlbuild_executable,
    )
