"""Runtime planning pipeline for `sqb dbt plan`."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.commands.connection_progress import (
    build_connection_progress_reporter,
)
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.cli.arg_parser import parse_dbt_execution_args
from sqlbuild.integrations.dbt.helpers.cli.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.helpers.cli.mode import enforce_dbt_interop_standard_mode
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.manifest.core import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.planning.orchestration import plan_dbt_interop_command
from sqlbuild.integrations.dbt.helpers.planning.runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
    resolve_dbt_vars_mapping,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandResult,
    DbtInteropPlan,
    DbtInteropRoutedArgs,
    DbtModelPlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import (
    append_manifest_seed_warnings,
    append_stale_out_of_selection_warning,
    build_dbt_non_model_run_unique_ids,
    build_dbt_pruned_seed_unique_ids,
    build_dbt_pruned_test_unique_ids,
    build_unblocked_sqlbuild_model_names,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import (
    build_dbt_model_plan_output,
    build_sqlbuild_plan_output,
    dbt_failure_detail,
)
from sqlbuild.integrations.dbt.shared.helpers.executable import resolve_dbt_executable
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.targets import resolve_effective_force


def plan_dbt_interop_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    dbt_runner: DbtRunner | None = None,
    dbt_executable: str | None = None,
    sqlbuild_executable: str = "sqb",
    no_sql_validation: bool = False,
    on_progress: Callable[[str], None] | None = None,
    progress_stream: TextIO | None = None,
    use_color: bool = False,
) -> DbtInteropPlan:
    """Build a dbt interop plan from real project files and dbt artifacts."""

    dbt_executable = dbt_executable or resolve_dbt_executable()
    routed: DbtInteropRoutedArgs = route_dbt_interop_args(
        command=DbtInteropCommand.PLAN,
        parsed=parse_dbt_execution_args(command=DbtInteropCommand.PLAN, args=args),
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    effective_force: bool = resolve_effective_force(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
        cli_force="--force" in routed.sqlbuild_args,
    )
    effective_sqlbuild_args: tuple[str, ...] = (
        routed.sqlbuild_args
        if not effective_force or "--force" in routed.sqlbuild_args
        else (*routed.sqlbuild_args, "--force")
    )
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=routed.dbt_args,
    )
    dbt_vars: dict[str, object] = resolve_dbt_vars_mapping(
        project_config=discovered_inputs.project_config.dbt,
        local_config=discovered_inputs.local_config.dbt,
        dbt_args=routed.dbt_args,
    )
    runner: DbtRunner = dbt_runner or DbtRunner(dbt_executable=dbt_executable)
    dbt_compile_start: float = time.monotonic()
    _report_progress(on_progress, "Compiling dbt project...")
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed",
            help=dbt_failure_detail(compile_result),
        )
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
    connection_progress: Any = (
        build_connection_progress_reporter(
            adapter_name=adapter_name,
            stream=progress_stream,
            use_color=use_color,
        )
        if progress_stream is not None
        else None
    )
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=dbt_vars,
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
        command=DbtInteropCommand.PLAN,
        project=project,
        manifest=manifest,
        graph=graph,
        dbt_runner=runner,
        dbt_options=dbt_options,
        select=routed.select,
        exclude=routed.exclude,
        dbt_command_args=routed.dbt_args,
        sqlbuild_command_args=effective_sqlbuild_args,
        dbt_executable=dbt_executable,
        sqlbuild_executable=sqlbuild_executable,
    )
    _report_progress(
        on_progress,
        f"Resolved dbt and SQLBuild selection. ({time.monotonic() - selection_start:.2f}s)",
    )
    dbt_model_plan: DbtModelPlanningResult | None = build_dbt_model_plan_output(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        project=project,
        adapter=adapter,
        adapter_name=adapter_name,
        manifest=manifest,
        graph=graph,
        candidate_unique_ids=tuple(
            sorted(
                frozenset(
                    (
                        *plan.dbt_selected_unique_ids,
                        *plan.selection.dbt_required_unique_ids,
                    )
                )
            )
        ),
        selected_unique_ids=plan.dbt_selected_unique_ids,
        full_refresh="--full-refresh" in routed.dbt_args,
        force=effective_force,
        on_connection_start=(
            None if connection_progress is None else connection_progress.on_connection_start
        ),
        on_connection_complete=(
            None if connection_progress is None else connection_progress.on_connection_complete
        ),
        on_connection_error=(
            None if connection_progress is None else connection_progress.on_connection_error
        ),
        on_progress=on_progress,
    )
    if dbt_model_plan is not None:
        plan = replace(plan, dbt_model_plan=dbt_model_plan)
        plan = append_stale_out_of_selection_warning(plan=plan, dbt_model_plan=dbt_model_plan)
    plan = append_manifest_seed_warnings(plan=plan, manifest=manifest)
    plan = replace(
        plan,
        dbt_non_model_run_unique_ids=build_dbt_non_model_run_unique_ids(
            command=DbtInteropCommand.BUILD,
            plan=plan,
        ),
        dbt_pruned_seed_unique_ids=build_dbt_pruned_seed_unique_ids(
            command=DbtInteropCommand.BUILD,
            plan=plan,
        ),
        dbt_pruned_test_unique_ids=build_dbt_pruned_test_unique_ids(
            command=DbtInteropCommand.BUILD,
            plan=plan,
        ),
    )
    sqlbuild_plan_output: PlanOutput | None = build_sqlbuild_plan_output(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        project=project,
        adapter=adapter,
        adapter_name=adapter_name,
        selected_model_names=build_unblocked_sqlbuild_model_names(plan),
        required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
        forced_stale_model_names=(
            plan.dbt_model_plan.stale_sqlbuild_model_names
            if plan.dbt_model_plan is not None
            else ()
        ),
        sqlbuild_args=effective_sqlbuild_args,
        on_progress=on_progress,
        on_connection_start=(
            None if connection_progress is None else connection_progress.on_connection_start
        ),
        on_connection_complete=(
            None if connection_progress is None else connection_progress.on_connection_complete
        ),
        on_connection_error=(
            None if connection_progress is None else connection_progress.on_connection_error
        ),
        dependency_baseline_entries=(),
    )
    if sqlbuild_plan_output is not None:
        plan = replace(plan, sqlbuild_plan_output=sqlbuild_plan_output)
    _report_progress(
        on_progress,
        f"Generated dbt interop plan. ({time.monotonic() - selection_start:.2f}s)",
    )
    return plan


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
