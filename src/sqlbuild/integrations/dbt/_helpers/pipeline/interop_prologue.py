"""Shared prologue phases for dbt interop pipelines."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.integrations.dbt._helpers.pipeline.plan_output import dbt_failure_detail
from sqlbuild.integrations.dbt.classes.dbt_compile_reference_resolver import (
    DbtCompileReferenceResolver,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.main.cli._enforce_direct_mode import (
    enforce_dbt_interop_direct_mode,
)
from sqlbuild.integrations.dbt.main.cli._parse_execution_args import parse_dbt_execution_args
from sqlbuild.integrations.dbt.main.cli._resolve_executable import resolve_dbt_executable
from sqlbuild.integrations.dbt.main.cli._route_interop_args import route_dbt_interop_args
from sqlbuild.integrations.dbt.main.config._resolve_plan_options import resolve_dbt_plan_options
from sqlbuild.integrations.dbt.main.config._resolve_vars_mapping import resolve_dbt_vars_mapping
from sqlbuild.integrations.dbt.main.graph._build_combined_graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.main.manifest._load_manifest_index import (
    load_manifest_index as load_dbt_manifest_index,
)
from sqlbuild.integrations.dbt.main.manifest._resolve_manifest_path import (
    resolve_dbt_manifest_path,
)
from sqlbuild.integrations.dbt.main.planning._plan_interop_command import plan_dbt_interop_command
from sqlbuild.integrations.dbt.main.runtime._report_progress import report_progress
from sqlbuild.integrations.dbt.main.runtime._resolve_interop_adapter import (
    resolve_dbt_interop_adapter,
)
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandResult,
    DbtInteropCommandArgs,
    DbtInteropCompiledProject,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlan,
    DbtInteropPlanResolution,
    DbtInteropRoutedArgs,
    DbtManifestIndex,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def resolve_dbt_execution_invocation(
    request: DbtInteropExecutionRequest,
) -> DbtInteropInvocation:
    """Route args, discover the project, and resolve dbt options for execution."""

    dbt_executable: str = request.dbt_executable or resolve_dbt_executable()
    output_stream: TextIO = request.progress_stream or sys.stdout
    routed: DbtInteropRoutedArgs = route_dbt_interop_args(
        command=request.command,
        parsed=parse_dbt_execution_args(command=request.command, args=request.args),
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=request.project_dir
    )
    enforce_dbt_interop_direct_mode(discovered_inputs=discovered_inputs)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=request.project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=routed.dbt_args,
    )
    dbt_vars: dict[str, object] = resolve_dbt_vars_mapping(
        project_config=discovered_inputs.project_config.dbt,
        local_config=discovered_inputs.local_config.dbt,
        dbt_args=routed.dbt_args,
    )
    return DbtInteropInvocation(
        dbt_executable=dbt_executable,
        output_stream=output_stream,
        dbt_output_stream=request.dbt_stdout_stream or output_stream,
        routed=routed,
        discovered_inputs=discovered_inputs,
        effective_sqlbuild_args=routed.sqlbuild_args,
        dbt_options=dbt_options,
        dbt_vars=dbt_vars,
        runner=request.dbt_runner or DbtRunner(dbt_executable=dbt_executable),
    )


def load_compiled_dbt_manifest(
    *,
    runner: DbtRunner,
    dbt_options: DbtCliOptions,
    full_refresh: bool,
    on_progress: Callable[[str], None] | None,
) -> DbtManifestIndex:
    """Compile the dbt project and load its manifest index."""

    dbt_compile_start: float = time.monotonic()
    report_progress(on_progress=on_progress, message="Compiling dbt project...")
    compile_result: DbtCommandResult = runner.compile(
        options=dbt_options,
        full_refresh=full_refresh,
    )
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError("dbt compile failed", help=dbt_failure_detail(compile_result))
    report_progress(
        on_progress=on_progress,
        message=f"Compiled dbt project. ({time.monotonic() - dbt_compile_start:.2f}s)",
    )
    manifest_start: float = time.monotonic()
    report_progress(on_progress=on_progress, message="Loading dbt manifest...")
    manifest_path: Path = resolve_dbt_manifest_path(options=dbt_options)
    manifest: DbtManifestIndex = load_dbt_manifest_index(manifest_path=manifest_path)
    report_progress(
        on_progress=on_progress,
        message=f"Loaded dbt manifest. ({time.monotonic() - manifest_start:.2f}s)",
    )
    return manifest


def compile_dbt_interop_project(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    manifest: DbtManifestIndex,
    dbt_vars: dict[str, object],
    no_sql_validation: bool,
    on_progress: Callable[[str], None] | None,
) -> DbtInteropCompiledProject:
    """Resolve the adapter and compile the SQLBuild project against the dbt manifest."""

    sqlbuild_compile_start: float = time.monotonic()
    report_progress(on_progress=on_progress, message="Compiling SQLBuild project...")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(
        adapter_name=adapter_name, project_dir=project_dir
    )
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=dbt_vars,
        external_sql_reference_resolver=DbtCompileReferenceResolver(dbt_manifest=manifest),
    )
    report_progress(
        on_progress=on_progress,
        message=f"Compiled SQLBuild project. ({time.monotonic() - sqlbuild_compile_start:.2f}s)",
    )
    return DbtInteropCompiledProject(adapter_name=adapter_name, adapter=adapter, project=project)


def resolve_dbt_interop_plan(
    *,
    command: DbtInteropCommand,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    sqlbuild_executable: str,
    on_progress: Callable[[str], None] | None,
) -> DbtInteropPlanResolution:
    """Build the combined dbt graph and resolve dbt and SQLBuild selection."""

    graph_start: float = time.monotonic()
    report_progress(on_progress=on_progress, message="Building dbt interop graph...")
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=compiled.project)
    report_progress(
        on_progress=on_progress,
        message=f"Built dbt interop graph. ({time.monotonic() - graph_start:.2f}s)",
    )
    selection_start: float = time.monotonic()
    report_progress(on_progress=on_progress, message="Resolving dbt and SQLBuild selection...")
    plan: DbtInteropPlan = plan_dbt_interop_command(
        command=command,
        project=compiled.project,
        manifest=manifest,
        graph=graph,
        dbt_runner=invocation.runner,
        dbt_options=invocation.dbt_options,
        command_args=DbtInteropCommandArgs(
            select=tuple(invocation.routed.select),
            exclude=tuple(invocation.routed.exclude),
            dbt_command_args=tuple(invocation.routed.dbt_args),
            sqlbuild_command_args=tuple(invocation.effective_sqlbuild_args),
            dbt_executable=invocation.dbt_executable,
            sqlbuild_executable=sqlbuild_executable,
        ),
    )
    report_progress(
        on_progress=on_progress,
        message=f"Resolved dbt and SQLBuild selection. ({time.monotonic() - selection_start:.2f}s)",
    )
    return DbtInteropPlanResolution(graph=graph, plan=plan)
