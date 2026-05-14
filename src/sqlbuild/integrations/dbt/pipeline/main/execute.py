"""Runtime execution pipeline for dbt interop execution commands."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.connection_progress import build_connection_progress_reporter
from sqlbuild.cli.commands.main.dbt_sqlbuild_work import execute_dbt_sqlbuild_work
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.helpers.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.plan_orchestration import (
    plan_dbt_interop_command,
    resolve_sqlbuild_test_actions,
)
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
    DbtInteropPlan,
    DbtInteropRoutedArgs,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import (
    build_deferred_dbt_relations,
    build_merged_dbt_execution_argv,
    execute_dbt_commands,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import (
    build_sqlbuild_plan_output,
    dbt_failure_detail,
    resolve_connection_config,
)
from sqlbuild.integrations.dbt.pipeline.main.render_plan import render_dbt_interop_plan
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSqlbuildTestAction
from sqlbuild.shared.helpers.display import DisplayOptions
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def execute_dbt_interop_from_project(
    *,
    command: DbtInteropCommand,
    project_dir: Path,
    args: tuple[str, ...],
    dbt_runner: DbtRunner | None = None,
    dbt_executable: str = "dbt",
    sqlbuild_executable: str = "sqb",
    no_sql_validation: bool = False,
    fail_fast: bool = False,
    on_progress: Callable[[str], None] | None = None,
    progress_stream: TextIO | None = None,
    dbt_stdout_stream: TextIO | None = None,
    use_color: bool = False,
    verbose: bool = False,
    json_output: bool = False,
) -> int:
    """Execute dbt first, then SQLBuild, for downstream-only interop commands."""

    if command not in (DbtInteropCommand.RUN, DbtInteropCommand.BUILD, DbtInteropCommand.TEST):
        raise ValueError(f"unsupported dbt interop execution command: {command}")

    output_stream: TextIO = progress_stream or sys.stdout
    dbt_output_stream: TextIO = dbt_stdout_stream or output_stream
    routed: DbtInteropRoutedArgs = route_dbt_interop_args(command=command, args=args)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=routed.dbt_args,
    )
    runner: DbtRunner = dbt_runner or DbtRunner(dbt_executable=dbt_executable)

    dbt_compile_start: float = time.monotonic()
    _report_progress(on_progress, "Compiling dbt project...")
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError("dbt compile failed", help=dbt_failure_detail(compile_result))
    _report_progress(
        on_progress, f"Compiled dbt project. ({time.monotonic() - dbt_compile_start:.2f}s)"
    )

    manifest_start: float = time.monotonic()
    _report_progress(on_progress, "Loading dbt manifest...")
    manifest_path: Path = resolve_dbt_manifest_path(options=dbt_options)
    manifest: DbtManifestIndex = load_dbt_manifest_index(manifest_path=manifest_path)
    _report_progress(
        on_progress, f"Loaded dbt manifest. ({time.monotonic() - manifest_start:.2f}s)"
    )

    sqlbuild_compile_start: float = time.monotonic()
    _report_progress(on_progress, "Compiling SQLBuild project...")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(adapter_name, project_dir=project_dir)
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        external_sql_reference_resolver=DbtCompileReferenceResolver(dbt_manifest=manifest),
    )
    _report_progress(
        on_progress,
        f"Compiled SQLBuild project. ({time.monotonic() - sqlbuild_compile_start:.2f}s)",
    )

    graph_start: float = time.monotonic()
    _report_progress(on_progress, "Building dbt interop graph...")
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    _report_progress(
        on_progress, f"Built dbt interop graph. ({time.monotonic() - graph_start:.2f}s)"
    )

    selection_start: float = time.monotonic()
    _report_progress(on_progress, "Resolving dbt and SQLBuild selection...")
    plan: DbtInteropPlan = plan_dbt_interop_command(
        command=command,
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
    _report_progress(
        on_progress,
        f"Resolved dbt and SQLBuild selection. ({time.monotonic() - selection_start:.2f}s)",
    )
    merged_dbt_argv: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=command,
        options=dbt_options,
        routed_args=routed.dbt_args,
        plan=plan,
    )
    if not json_output:
        display_plan: DbtInteropPlan = plan
        if merged_dbt_argv is not None:
            display_plan = replace(
                plan,
                dbt_command_argv=merged_dbt_argv,
                supplemental_dbt_command_argvs=(),
            )
        rendered_plan: str = render_dbt_interop_plan(
            display_plan,
            json_output=False,
            use_color=use_color,
            display_options=DisplayOptions(max_entries_per_section=None if verbose else 50),
        )
        output_stream.write(rendered_plan + "\n\n")
        output_stream.flush()

    dbt_exit_code: int = execute_dbt_commands(
        runner=runner,
        options=dbt_options,
        merged_argv=merged_dbt_argv,
        progress_stream=output_stream,
        stdout_stream=dbt_output_stream,
        stderr_stream=output_stream,
        use_color=use_color,
    )
    if dbt_exit_code != 0:
        return dbt_exit_code
    if plan.sqlbuild_skip_reason is not None:
        _report_progress(on_progress, "No SQLBuild work selected.")
        return 0
    output_stream.write("\n")
    output_stream.flush()

    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
    )
    connection_progress: Any = build_connection_progress_reporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    plan_output: PlanOutput | None = build_sqlbuild_plan_output(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        project=project,
        adapter=adapter,
        adapter_name=adapter_name,
        selected_model_names=plan.selection.sqlbuild_model_names,
        required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
        sqlbuild_args=routed.sqlbuild_args,
        on_progress=None,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        deferred_relations=build_deferred_dbt_relations(plan=plan, manifest=manifest),
    )
    if plan_output is None:
        return 0

    actions: tuple[DbtInteropSqlbuildTestAction, ...] = ()
    if command == DbtInteropCommand.TEST:
        actions = resolve_sqlbuild_test_actions(select=routed.select)
    return execute_dbt_sqlbuild_work(
        command=command,
        plan_output=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        adapter_name=adapter_name,
        project=project,
        project_dir=project_dir,
        fail_fast=fail_fast,
        verbose=verbose,
        actions=actions,
        output_stream=output_stream,
        use_color=use_color,
    )


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
