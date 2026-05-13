"""Runtime execution pipeline for `sqb dbt run` and `sqb dbt build`."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import (
    BuildProgressCallbacks,
    format_build_footer,
    format_build_header,
)
from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import write_runtime_target
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredDbtManifestFile, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.plan_orchestration import plan_dbt_interop_command
from sqlbuild.integrations.dbt.helpers.plan_runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner, build_dbt_command_argv
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtInteropPlan,
    DbtInteropRoutedArgs,
    DbtLsNode,
    DbtManifestIndex,
    DbtManifestModel,
)
from sqlbuild.integrations.dbt.pipeline.main.plan import (
    _build_sqlbuild_plan_output,
    _dbt_failure_detail,
    _resolve_connection_config,
)
from sqlbuild.integrations.dbt.pipeline.main.render_plan import render_dbt_interop_plan
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.shared.helpers.colors import blue_bold, dim, orange_bold
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

    if command not in (DbtInteropCommand.RUN, DbtInteropCommand.BUILD):
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
        raise DbtInteropRuntimeError("dbt compile failed", help=_dbt_failure_detail(compile_result))
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
    _report_progress(
        on_progress,
        f"Compiled SQLBuild project. ({time.monotonic() - sqlbuild_compile_start:.2f}s)",
    )

    graph_start: float = time.monotonic()
    _report_progress(on_progress, "Building dbt interop graph...")
    graph = build_dbt_combined_graph(manifest=manifest, project=project)
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
    merged_dbt_argv: tuple[str, ...] | None = _build_merged_dbt_execution_argv(
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

    dbt_exit_code: int = _execute_dbt_commands(
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

    connection_config: dict[str, object] = _resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    plan_output: PlanOutput | None = _build_sqlbuild_plan_output(
        project_dir=project_dir,
        discovered_inputs=discovered_with_manifest,
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
        deferred_relations=_build_deferred_dbt_relations(plan=plan, manifest=manifest),
    )
    if plan_output is None:
        return 0

    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color, verbose=verbose, debug=False
    )
    effective_concurrency: int = project.settings.concurrency
    header: str = format_build_header(
        command=f"sqb {command.value}", target=None, concurrency=effective_concurrency
    )
    execution_label: str = blue_bold("SQLBuild execution") if use_color else "SQLBuild execution"
    header_detail: str = dim(header) if use_color else header
    output_stream.write(f"{execution_label}  {header_detail}\n\n")
    output_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    result: BuildExecutionResult = run_build_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        settings=project.settings,
        run_id=project.run_id,
        run_tests=command == DbtInteropCommand.BUILD,
        run_audits=command == DbtInteropCommand.BUILD,
        fail_fast=fail_fast,
        max_concurrency=effective_concurrency,
        on_node_start=callbacks.on_node_start,
        on_node_complete=callbacks.on_node_complete,
        on_sub_progress=callbacks.on_sub_progress,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
    )
    write_runtime_target(target_dir=project_dir / "target", plan_output=plan_output, result=result)
    footer: str = format_build_footer(result=result, elapsed=callbacks.elapsed, use_color=use_color)
    output_stream.write("\n" + footer + "\n")
    output_stream.flush()
    return 0 if result.status == BuildStatus.SUCCESS else 1


def _execute_dbt_commands(
    *,
    runner: DbtRunner,
    options: DbtCliOptions,
    merged_argv: tuple[str, ...] | None,
    progress_stream: TextIO,
    stdout_stream: TextIO,
    stderr_stream: TextIO,
    use_color: bool,
) -> int:
    if merged_argv is None:
        progress_stream.write("Skipping dbt: no dbt work selected.\n")
        progress_stream.flush()
        return 0
    argv: tuple[str, ...] = merged_argv
    dbt_execution_label: str = orange_bold("dbt execution") if use_color else "dbt execution"
    dbt_execution_detail_text: str = " ".join(argv[:2]) if len(argv) >= 2 else argv[0]
    dbt_execution_detail: str = (
        dim(dbt_execution_detail_text) if use_color else dbt_execution_detail_text
    )
    progress_stream.write(f"{dbt_execution_label}  {dbt_execution_detail}\n\n")
    progress_stream.write(f"Running dbt: {' '.join(argv)}\n")
    progress_stream.flush()
    result: DbtCommandResult = runner.invoke(argv=argv, cwd=options.project_dir)
    if result.stdout:
        stdout_stream.write(result.stdout)
        stdout_stream.flush()
    if result.stderr:
        stderr_stream.write(result.stderr)
        stderr_stream.flush()
    return result.returncode


def _build_merged_dbt_execution_argv(
    *,
    command: DbtInteropCommand,
    options: DbtCliOptions,
    routed_args: tuple[str, ...],
    plan: DbtInteropPlan,
) -> tuple[str, ...] | None:
    if not plan.dbt_selected_unique_ids and not plan.dbt_required_selector_terms:
        return None
    merged_args: tuple[str, ...] = _merge_dbt_select_terms(
        args=_strip_resolved_dbt_options(routed_args),
        extra_terms=plan.dbt_required_selector_terms,
    )
    return build_dbt_command_argv(
        dbt_executable=plan.dbt_command_argv[0],
        command=command.value,
        options=options,
        args=merged_args,
    )


def _strip_resolved_dbt_options(args: tuple[str, ...]) -> tuple[str, ...]:
    value_flags: frozenset[str] = frozenset(
        {"--project-dir", "--profiles-dir", "--target", "--target-path", "--vars", "--state"}
    )
    stripped: list[str] = []
    index: int = 0
    while index < len(args):
        arg: str = args[index]
        if arg in value_flags:
            index += 2
            continue
        if arg == "--defer":
            index += 1
            continue
        stripped.append(arg)
        index += 1
    return tuple(stripped)


def _merge_dbt_select_terms(
    *, args: tuple[str, ...], extra_terms: tuple[str, ...]
) -> tuple[str, ...]:
    if not extra_terms:
        return args
    if "--select" not in args:
        return (*args, "--select", *extra_terms)

    merged: list[str] = []
    index: int = 0
    inserted: bool = False
    while index < len(args):
        token: str = args[index]
        merged.append(token)
        index += 1
        if token != "--select":
            continue
        while index < len(args) and not args[index].startswith("--"):
            merged.append(args[index])
            index += 1
        merged.extend(term for term in extra_terms if term not in merged)
        inserted = True
    if not inserted:
        merged.extend(("--select", *extra_terms))
    return tuple(merged)


def _build_deferred_dbt_relations(
    *, plan: DbtInteropPlan, manifest: DbtManifestIndex
) -> dict[str, RelationInfo]:
    relations: dict[str, RelationInfo] = {}
    unique_ids: set[str] = set(plan.selection.dbt_required_unique_ids)
    node: DbtLsNode
    for node in plan.dbt_selected_nodes:
        if node.resource_type == "model":
            unique_ids.add(node.unique_id)
    unique_id: str
    for unique_id in unique_ids:
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
        if model is None:
            continue
        relation: RelationInfo = RelationInfo(
            database=model.database,
            schema=model.schema,
            name=model.name,
            relation_type="table",
        )
        relations[model.name] = relation
        relations[f"{model.package_name}.{model.name}"] = relation
    return relations


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
