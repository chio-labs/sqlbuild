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
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.main.plan_work import plan_has_executable_work
from sqlbuild.compiler.planner.models import DependencyBaselinePlanEntry, PlanOutput
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.helpers.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.fingerprinting import try_write_dbt_node_fingerprint
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.mode import enforce_dbt_interop_standard_mode
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
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandExecutionResult,
    DbtCommandResult,
    DbtExecutionOutcome,
    DbtInteropPlan,
    DbtInteropRoutedArgs,
    DbtModelPlanningResult,
    DbtNodeExecutionResult,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.dependency_baseline import (
    build_dbt_native_dependency_baseline_entries,
    dependency_baseline_unique_ids,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import (
    build_dbt_execution_outcome,
    build_dbt_non_model_run_unique_ids,
    build_dbt_pruned_seed_unique_ids,
    build_dbt_pruned_test_unique_ids,
    build_deferred_dbt_relations,
    build_merged_dbt_execution_argv,
    dbt_blocked_exit_code,
    execute_dbt_commands,
)
from sqlbuild.integrations.dbt.pipeline.helpers.missing_relations import (
    find_and_report_missing_dbt_relation_blocks,
    missing_dbt_relations_exit_code,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import (
    build_dbt_model_plan_output,
    build_sqlbuild_plan_output,
    dbt_failure_detail,
    resolve_connection_config,
)
from sqlbuild.integrations.dbt.pipeline.helpers.reuse_execute import (
    execute_dbt_complete_reuse_plan,
    execute_dbt_seeded_reuse_plan,
    has_physical_dbt_reuse_work,
)
from sqlbuild.integrations.dbt.pipeline.helpers.reuse_output import (
    format_dbt_reuse_execution_output,
)
from sqlbuild.integrations.dbt.pipeline.helpers.reuse_plan import (
    build_dbt_dependency_baseline_plan_output,
    build_dbt_reuse_plan_output,
)
from sqlbuild.integrations.dbt.pipeline.helpers.source_freshness import (
    append_dbt_source_freshness_records,
)
from sqlbuild.integrations.dbt.pipeline.main.render_plan import render_dbt_interop_plan
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
    DbtInteropSkipReason,
    DbtInteropSqlbuildTestAction,
)
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.display import DisplayOptions
from sqlbuild.shared.helpers.status import TransientStatusReporter
from sqlbuild.spec.models.project import DbtReuseFromConfig, resolve_effective_adapter_name


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
        raise DbtInteropArgumentError(f"unsupported dbt interop execution command: {command}")

    output_stream: TextIO = progress_stream or sys.stdout
    dbt_output_stream: TextIO = dbt_stdout_stream or output_stream
    routed: DbtInteropRoutedArgs = route_dbt_interop_args(command=command, args=args)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
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
    connection_progress: Any = build_connection_progress_reporter(
        adapter_name=adapter_name,
        stream=output_stream,
        use_color=use_color,
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
        full_refresh="--full-refresh" in routed.dbt_args,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
    )
    if dbt_model_plan is not None:
        plan = replace(plan, dbt_model_plan=dbt_model_plan)
    reuse_git_ref: str | None = None
    reuse_from: DbtReuseFromConfig = discovered_inputs.project_config.dbt.reuse_from
    if reuse_from.git_ref is not None and reuse_from.generate_schema_name_override is not None:
        reuse_git_ref = reuse_from.git_ref
    has_explicit_dbt_reuse_scope: bool = bool(
        plan.dbt_selected_unique_ids
        or plan.selection.dbt_required_unique_ids
        or plan.selection.dbt_anchor_unique_ids_by_term
    )
    reuse_plan_start: float | None = None
    if reuse_git_ref is not None and has_explicit_dbt_reuse_scope:
        reuse_plan_start = time.monotonic()
        _report_progress(on_progress, f"Planning dbt reuse from git ref '{reuse_git_ref}'...")
    dbt_reuse_plan: DbtReusePlanningResult | None = None
    if has_explicit_dbt_reuse_scope:
        dbt_reuse_plan = build_dbt_reuse_plan_output(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            current_manifest=manifest,
            adapter=adapter,
            adapter_name=adapter_name,
            dbt_model_plan=dbt_model_plan,
            plan=plan,
            dbt_options=dbt_options,
            runner=runner,
        )
    if reuse_plan_start is not None:
        _report_progress(
            on_progress,
            f"Planned dbt reuse from git ref '{reuse_git_ref}'. "
            f"({time.monotonic() - reuse_plan_start:.2f}s)",
        )
    if dbt_reuse_plan is not None:
        plan = replace(plan, dbt_reuse_plan=dbt_reuse_plan)
    dependency_baseline_ids: tuple[str, ...] = dependency_baseline_unique_ids(
        project=project,
        manifest=manifest,
        plan=plan,
    )
    dependency_baseline_model_plan: DbtModelPlanningResult | None = None
    if dependency_baseline_ids:
        dependency_baseline_model_plan = build_dbt_model_plan_output(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=project,
            adapter=adapter,
            adapter_name=adapter_name,
            manifest=manifest,
            graph=graph,
            candidate_unique_ids=dependency_baseline_ids,
            full_refresh="--full-refresh" in routed.dbt_args,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
        )
    dbt_dependency_baseline_plan: DbtReusePlanningResult | None = (
        build_dbt_dependency_baseline_plan_output(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            current_manifest=manifest,
            adapter=adapter,
            adapter_name=adapter_name,
            dbt_model_plan=dependency_baseline_model_plan,
            scoped_unique_ids=dependency_baseline_ids,
            dbt_options=dbt_options,
            runner=runner,
        )
    )
    if dbt_dependency_baseline_plan is not None:
        plan = replace(plan, dbt_dependency_baseline_plan=dbt_dependency_baseline_plan)
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = (
        build_dbt_native_dependency_baseline_entries(
            plan=dbt_dependency_baseline_plan,
            destination_target_name=project.effective_target_name,
        )
    )
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    dbt_fingerprint_warnings: list[str] = []
    reused_dbt_unique_ids: tuple[str, ...] = ()
    baseline_reused_dbt_unique_ids: tuple[str, ...] = ()
    if has_physical_dbt_reuse_work(plan):
        reuse_status: TransientStatusReporter | None = None
        if hasattr(output_stream, "isatty") and output_stream.isatty():
            reuse_status = TransientStatusReporter(stream=output_stream, use_color=use_color)
            reuse_status.start("Preparing dbt reuse relations...")
        reuse_connection: object = adapter.connect(connection_config)
        try:
            reused_dbt_unique_ids = execute_dbt_complete_reuse_plan(
                adapter=adapter,
                connection=reuse_connection,
                manifest=manifest,
                plan=plan,
                run_id=project.run_id,
                fingerprint_database=project.effective_target_database,
                fingerprint_schema=project.effective_target_schema,
                target_name=project.effective_target_name,
                warnings=dbt_fingerprint_warnings,
            )
            baseline_reused_dbt_unique_ids = execute_dbt_seeded_reuse_plan(
                adapter=adapter,
                connection=reuse_connection,
                manifest=manifest,
                plan=plan,
            )
        finally:
            if reuse_status is not None:
                reuse_status.close()
            adapter.close(reuse_connection)
    plan = replace(
        plan,
        dbt_non_model_run_unique_ids=build_dbt_non_model_run_unique_ids(
            command=command,
            plan=plan,
        ),
        dbt_pruned_seed_unique_ids=build_dbt_pruned_seed_unique_ids(
            command=command,
            plan=plan,
        ),
        dbt_pruned_test_unique_ids=build_dbt_pruned_test_unique_ids(
            command=command,
            plan=plan,
        ),
    )
    merged_dbt_argv: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=command,
        options=dbt_options,
        routed_args=routed.dbt_args,
        plan=plan,
        replay_on_change=discovered_inputs.project_config.dbt.replay_on_change,
    )
    missing_dbt_relation_blocked_models: dict[str, tuple[DbtManifestModel, ...]] = {}
    if merged_dbt_argv is None and plan.sqlbuild_skip_reason is None:
        missing_dbt_relation_blocked_models = find_and_report_missing_dbt_relation_blocks(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=project,
            manifest=manifest,
            adapter=adapter,
            adapter_name=adapter_name,
            selected_model_names=plan.selection.sqlbuild_model_names,
            dbt_unique_ids_selected_for_execution=frozenset(
                (*plan.dbt_selected_unique_ids, *plan.selection.dbt_required_unique_ids)
                + tuple(dependency_baseline_ids)
            ),
            output_stream=output_stream,
        )
        sqlbuild_plan_output: PlanOutput | None = build_sqlbuild_plan_output(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=project,
            adapter=adapter,
            adapter_name=adapter_name,
            selected_model_names=plan.selection.sqlbuild_model_names,
            required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
            external_blocked_model_names=(
                *(
                    plan.dbt_model_plan.blocked_sqlbuild_model_names
                    if plan.dbt_model_plan is not None
                    else ()
                ),
                *missing_dbt_relation_blocked_models,
            ),
            sqlbuild_args=routed.sqlbuild_args,
            on_progress=None,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
            deferred_relations=build_deferred_dbt_relations(plan=plan, manifest=manifest),
            dependency_baseline_entries=dependency_baseline_entries,
        )
        if sqlbuild_plan_output is not None:
            plan = replace(plan, sqlbuild_plan_output=sqlbuild_plan_output)
    if not json_output:
        display_plan: DbtInteropPlan = plan
        if merged_dbt_argv is not None:
            display_plan = replace(
                plan,
                dbt_command_argv=merged_dbt_argv,
                supplemental_dbt_command_argvs=(),
            )
        elif (
            plan.dbt_model_plan is not None
            and plan.dbt_model_plan.current_unique_ids
            and not plan.dbt_model_plan.blocked_unique_ids
        ):
            display_plan = replace(
                plan,
                dbt_skip_reason=DbtInteropSkipReason.DBT_MODELS_CURRENT,
                supplemental_dbt_command_argvs=(),
            )
        rendered_plan: str = render_dbt_interop_plan(
            display_plan,
            json_output=False,
            use_color=use_color,
            display_options=DisplayOptions(max_entries_per_section=None if verbose else 10),
        )
        output_stream.write(rendered_plan + "\n\n")
        reuse_execution_output: str = ""
        if plan.dbt_reuse_plan is not None:
            reuse_execution_output = format_dbt_reuse_execution_output(
                plan=plan.dbt_reuse_plan,
                reused_unique_ids=reused_dbt_unique_ids,
                baseline_reused_unique_ids=baseline_reused_dbt_unique_ids,
                use_color=use_color,
                dbt_execution_will_run=merged_dbt_argv is not None,
                display_options=DisplayOptions(max_entries_per_section=None if verbose else 10),
            )
        if reuse_execution_output:
            output_stream.write(reuse_execution_output + "\n\n")
        output_stream.flush()

    buffered_dbt_results: list[DbtNodeExecutionResult] = []
    dbt_state_connection: object | None = None
    dbt_query_sql_by_unique_id: dict[str, str] = {
        unique_id: model.query_sql for unique_id, model in manifest.models_by_unique_id.items()
    }
    if project.settings.query_change_tracking and adapter_name != "duckdb":
        dbt_state_connection = adapter.connect(connection_config)

    def record_dbt_node_result(result: DbtNodeExecutionResult) -> None:
        if not project.settings.query_change_tracking:
            return
        if adapter_name == "duckdb":
            buffered_dbt_results.append(result)
            return
        if dbt_state_connection is None:
            return
        try_write_dbt_node_fingerprint(
            result=result,
            adapter=adapter,
            connection=dbt_state_connection,
            run_id=project.run_id,
            fingerprint_database=project.effective_target_database,
            fingerprint_schema=project.effective_target_schema,
            target_name=project.effective_target_name,
            warnings=dbt_fingerprint_warnings,
            query_sql=dbt_query_sql_by_unique_id.get(result.unique_id),
        )

    try:
        dbt_execution: DbtCommandExecutionResult = execute_dbt_commands(
            runner=runner,
            options=dbt_options,
            merged_argv=merged_dbt_argv,
            progress_stream=output_stream,
            stdout_stream=dbt_output_stream,
            stderr_stream=output_stream,
            use_color=use_color,
            on_node_result=record_dbt_node_result,
        )
    finally:
        if dbt_state_connection is not None:
            adapter.close(dbt_state_connection)

    if buffered_dbt_results and project.settings.query_change_tracking:
        duckdb_connection: object = adapter.connect(connection_config)
        try:
            dbt_result: DbtNodeExecutionResult
            for dbt_result in buffered_dbt_results:
                try_write_dbt_node_fingerprint(
                    result=dbt_result,
                    adapter=adapter,
                    connection=duckdb_connection,
                    run_id=project.run_id,
                    fingerprint_database=project.effective_target_database,
                    fingerprint_schema=project.effective_target_schema,
                    target_name=project.effective_target_name,
                    warnings=dbt_fingerprint_warnings,
                    query_sql=dbt_query_sql_by_unique_id.get(dbt_result.unique_id),
                )
        finally:
            adapter.close(duckdb_connection)
    warning: str
    for warning in dbt_fingerprint_warnings:
        output_stream.write(f"Warning: {warning}\n")
    if dbt_fingerprint_warnings:
        output_stream.flush()
    dbt_outcome: DbtExecutionOutcome = build_dbt_execution_outcome(
        plan=plan,
        graph=graph,
        node_results=dbt_execution.node_results,
    )
    if dbt_execution.returncode != 0 and not dbt_outcome.blocking_unique_ids:
        return dbt_execution.returncode
    if plan.sqlbuild_skip_reason is not None:
        output_stream.write("\n")
        output_stream.flush()
        _report_progress(on_progress, "No SQLBuild work selected.")
        exit_code: int = max(
            dbt_execution.returncode,
            dbt_blocked_exit_code(plan),
            missing_dbt_relations_exit_code(missing_dbt_relation_blocked_models),
        )
        if exit_code == 0:
            append_dbt_source_freshness_records(
                plan=plan,
                adapter=adapter,
                connection_config=connection_config,
                project=project,
            )
        return exit_code
    output_stream.write("\n")
    output_stream.flush()

    plan_output: PlanOutput | None = plan.sqlbuild_plan_output
    if plan_output is None or merged_dbt_argv is not None:
        missing_dbt_relation_blocked_models = find_and_report_missing_dbt_relation_blocks(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=project,
            manifest=manifest,
            adapter=adapter,
            adapter_name=adapter_name,
            selected_model_names=plan.selection.sqlbuild_model_names,
            dbt_unique_ids_selected_for_execution=frozenset(
                (
                    *plan.dbt_selected_unique_ids,
                    *plan.selection.dbt_required_unique_ids,
                    *dependency_baseline_ids,
                )
            ),
            output_stream=output_stream,
        )
        execution_plan_connection_progress: Any = build_connection_progress_reporter(
            adapter_name=adapter_name,
            stream=output_stream,
            blank_line_after_complete=True,
            use_color=use_color,
        )
        plan_output = build_sqlbuild_plan_output(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=project,
            adapter=adapter,
            adapter_name=adapter_name,
            selected_model_names=plan.selection.sqlbuild_model_names,
            required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
            forced_stale_model_names=dbt_outcome.stale_sqlbuild_model_names,
            external_blocked_model_names=(
                *dbt_outcome.blocked_sqlbuild_model_names,
                *missing_dbt_relation_blocked_models,
            ),
            sqlbuild_args=routed.sqlbuild_args,
            on_progress=None,
            on_connection_start=execution_plan_connection_progress.on_connection_start,
            on_connection_complete=execution_plan_connection_progress.on_connection_complete,
            on_connection_error=execution_plan_connection_progress.on_connection_error,
            deferred_relations=build_deferred_dbt_relations(plan=plan, manifest=manifest),
            dependency_baseline_entries=dependency_baseline_entries,
        )
    if plan_output is None:
        exit_code: int = max(
            dbt_execution.returncode,
            dbt_blocked_exit_code(plan),
            missing_dbt_relations_exit_code(missing_dbt_relation_blocked_models),
        )
        if exit_code == 0:
            append_dbt_source_freshness_records(
                plan=plan,
                adapter=adapter,
                connection_config=connection_config,
                project=project,
            )
        return exit_code
    if not plan_has_executable_work(plan_output):
        style: CliStyle = CliStyle(use_color=use_color)
        output_stream.write(
            style.muted("Skipping SQLBuild: selected models are already current.") + "\n"
        )
        output_stream.flush()
        exit_code = max(
            dbt_execution.returncode,
            dbt_blocked_exit_code(plan),
            missing_dbt_relations_exit_code(missing_dbt_relation_blocked_models),
        )
        if exit_code == 0:
            append_dbt_source_freshness_records(
                plan=plan,
                adapter=adapter,
                connection_config=connection_config,
                project=project,
            )
        return exit_code

    actions: tuple[DbtInteropSqlbuildTestAction, ...] = ()
    if command == DbtInteropCommand.TEST:
        actions = resolve_sqlbuild_test_actions(select=routed.select)
    sqlbuild_exit_code: int = execute_dbt_sqlbuild_work(
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
    if sqlbuild_exit_code != 0:
        return sqlbuild_exit_code
    append_dbt_source_freshness_records(
        plan=plan,
        adapter=adapter,
        connection_config=connection_config,
        project=project,
    )
    return max(
        dbt_execution.returncode,
        dbt_blocked_exit_code(plan),
        missing_dbt_relations_exit_code(missing_dbt_relation_blocked_models),
    )


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
