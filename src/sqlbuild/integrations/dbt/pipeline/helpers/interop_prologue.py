"""Shared prologue phases for dbt interop pipelines."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.cli.arg_parser import parse_dbt_execution_args
from sqlbuild.integrations.dbt.helpers.cli.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.helpers.cli.mode import enforce_dbt_interop_standard_mode
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner, resolve_dbt_executable
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.manifest.core import (
    build_dbt_manifest_index,
    load_dbt_manifest_index,
)
from sqlbuild.integrations.dbt.helpers.planning.orchestration import plan_dbt_interop_command
from sqlbuild.integrations.dbt.helpers.planning.runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
    resolve_dbt_vars_mapping,
)
from sqlbuild.integrations.dbt.helpers.profile.connection import resolve_connection_config
from sqlbuild.integrations.dbt.helpers.reuse.production_ref import compile_production_ref_manifest
from sqlbuild.integrations.dbt.helpers.runtime.progress import report_progress
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandResult,
    DbtComparisonPreparation,
    DbtInteropCommandArgs,
    DbtInteropCompiledProject,
    DbtInteropConnection,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlan,
    DbtInteropPlanResolution,
    DbtInteropRoutedArgs,
    DbtLsNode,
    DbtLsResult,
    DbtProductionRefCompileResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import dbt_failure_detail
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtSupportedResourceType
from sqlbuild.spec.models.project import DbtProductionRefConfig, resolve_effective_adapter_name
from sqlbuild.spec.models.targets import resolve_effective_force


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
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    effective_force: bool = resolve_effective_force(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
        cli_force="--force" in routed.sqlbuild_args,
    )
    effective_sqlbuild_args: tuple[str, ...] = _with_effective_force(
        args=routed.sqlbuild_args,
        force=effective_force,
    )
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
        effective_force=effective_force,
        effective_sqlbuild_args=effective_sqlbuild_args,
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


def _with_effective_force(*, args: tuple[str, ...], force: bool) -> tuple[str, ...]:
    if not force or "--force" in args:
        return args
    return (*args, "--force")


def prepare_dbt_comparison_manifests(
    *,
    project_dir: Path,
    dbt_args: tuple[str, ...],
    command_label: str,
    missing_config_code: str,
    on_progress: Callable[[str], None] | None,
) -> DbtComparisonPreparation:
    """Compile current and production-ref manifests for a comparison command."""

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    production_ref: DbtProductionRefConfig = discovered_inputs.project_config.dbt.production_ref
    if production_ref.git_ref is None or production_ref.generate_schema_name_override is None:
        raise DbtInteropConfigError(
            f"{command_label} requires [dbt.production_ref] to be configured",
            code=missing_config_code,
            help=(
                "Run sqb dbt init or set [dbt.production_ref].git_ref and "
                "generate_schema_name_override in sqlbuild_project.toml."
            ),
        )
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=dbt_args,
    )
    runner: DbtRunner = DbtRunner()
    report_progress(on_progress=on_progress, message="Compiling dbt project...")
    compile_start: float = time.monotonic()
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed",
            help=compile_result.stderr or compile_result.stdout,
        )
    report_progress(
        on_progress=on_progress,
        message=f"Compiled dbt project. ({time.monotonic() - compile_start:.2f}s)",
    )
    report_progress(on_progress=on_progress, message="Loading dbt manifest...")
    current_manifest: DbtManifestIndex = load_dbt_manifest_index(
        manifest_path=resolve_dbt_manifest_path(options=dbt_options)
    )
    report_progress(on_progress=on_progress, message="Loaded dbt manifest.")
    report_progress(
        on_progress=on_progress,
        message=f"Compiling dbt production ref git ref '{production_ref.git_ref}'...",
    )
    production_ref_start: float = time.monotonic()
    production_ref_compile: DbtProductionRefCompileResult = compile_production_ref_manifest(
        sqlbuild_project_dir=project_dir,
        dbt_options=dbt_options,
        production_ref=production_ref,
        runner=runner,
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(production_ref_compile.manifest_contents)
    )
    report_progress(
        on_progress=on_progress,
        message=f"Compiled dbt production ref git ref '{production_ref.git_ref}'. "
        f"({time.monotonic() - production_ref_start:.2f}s)",
    )
    return DbtComparisonPreparation(
        discovered_inputs=discovered_inputs,
        production_ref=production_ref,
        production_git_ref=production_ref.git_ref,
        dbt_options=dbt_options,
        runner=runner,
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
    )


def resolve_selected_dbt_model_nodes(
    *,
    runner: DbtRunner,
    dbt_options: DbtCliOptions,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[DbtLsNode, ...]:
    """List the dbt model nodes matching the command selection."""

    ls_result: DbtLsResult = runner.ls(
        options=dbt_options,
        select=select,
        exclude=exclude,
        resource_types=(DbtSupportedResourceType.MODEL,),
    )
    if ls_result.command.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt ls failed",
            help=ls_result.command.stderr or ls_result.command.stdout,
        )
    return ls_result.nodes


def connect_dbt_interop_warehouse(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    on_progress: Callable[[str], None] | None,
) -> DbtInteropConnection:
    """Resolve the adapter and open a warehouse connection with progress."""

    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(
        adapter_name=adapter_name, project_dir=project_dir
    )
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    report_progress(on_progress=on_progress, message=f"Connecting to {adapter_name}...")
    connect_start: float = time.monotonic()
    connection: Any = adapter.connect(connection_config)
    report_progress(
        on_progress=on_progress,
        message=f"Connected to {adapter_name}. ({time.monotonic() - connect_start:.2f}s)",
    )
    return DbtInteropConnection(
        adapter=adapter,
        adapter_name=adapter_name,
        connection_config=connection_config,
        connection=connection,
    )
