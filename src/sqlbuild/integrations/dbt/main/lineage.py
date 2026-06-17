"""Public dbt mixed-lineage entrypoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.lineage_args import parse_dbt_lineage_args
from sqlbuild.integrations.dbt.helpers.lineage_output import (
    format_dbt_lineage_json,
    format_dbt_lineage_list,
    format_dbt_lineage_tree,
)
from sqlbuild.integrations.dbt.helpers.lineage_selection import select_dbt_lineage_target
from sqlbuild.integrations.dbt.helpers.manifest import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.mode import enforce_dbt_interop_standard_mode
from sqlbuild.integrations.dbt.helpers.plan_runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandResult,
    DbtLineageArgs,
    DbtLineageGraph,
)
from sqlbuild.integrations.dbt.types import DbtLineageOutputFormat
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def build_dbt_lineage_output(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    use_color: bool,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Build formatted mixed dbt/SQLBuild lineage output."""

    lineage_args: DbtLineageArgs = parse_dbt_lineage_args(args)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=lineage_args.dbt_args,
    )
    runner: DbtRunner = DbtRunner(dbt_executable="dbt")
    _report_progress(on_progress, "Compiling dbt project...")
    dbt_compile_start: float = time.monotonic()
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed",
            help=compile_result.stderr or compile_result.stdout,
        )
    _report_progress(
        on_progress, f"Compiled dbt project. ({time.monotonic() - dbt_compile_start:.2f}s)"
    )
    _report_progress(on_progress, "Loading dbt manifest...")
    manifest: DbtManifestIndex = load_dbt_manifest_index(
        manifest_path=resolve_dbt_manifest_path(options=dbt_options)
    )
    _report_progress(on_progress, "Loaded dbt manifest.")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(adapter_name, project_dir=project_dir)
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=lineage_args.no_sql_validation,
        external_sql_reference_resolver=DbtCompileReferenceResolver(dbt_manifest=manifest),
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    lineage_graph: DbtLineageGraph = select_dbt_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=lineage_args.target,
        direction=lineage_args.direction,
        depth=lineage_args.depth,
    )
    if lineage_args.output_format == DbtLineageOutputFormat.JSON:
        return format_dbt_lineage_json(lineage_graph)
    if lineage_args.output_format == DbtLineageOutputFormat.LIST:
        return "\n" + format_dbt_lineage_list(lineage_graph, use_color=use_color) + "\n"
    return "\n" + format_dbt_lineage_tree(lineage_graph, use_color=use_color) + "\n"


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
