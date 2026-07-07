"""Execution, exit, and pre-execution planning phases for dbt interop."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.cli.commands.main.commands.connection_progress import (
    build_connection_progress_reporter,
)
from sqlbuild.cli.commands.main.commands.dbt_sqlbuild_work import (
    DbtSqlbuildWorkContext,
    execute_dbt_sqlbuild_work,
)
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkExecutionContext
from sqlbuild.compiler.planner.models import GraphNodeKey, PlanOutput
from sqlbuild.integrations.dbt.helpers.manifest.fingerprinting import (
    build_dbt_fingerprint_destination,
    try_write_dbt_node_fingerprint,
)
from sqlbuild.integrations.dbt.helpers.planning.graph_projection import dbt_graph_node_key
from sqlbuild.integrations.dbt.helpers.planning.model_identity import (
    build_dbt_write_identity_hashes,
)
from sqlbuild.integrations.dbt.helpers.planning.model_planning import (
    build_expected_dbt_model_version_hashes,
)
from sqlbuild.integrations.dbt.helpers.planning.orchestration import resolve_sqlbuild_test_actions
from sqlbuild.integrations.dbt.helpers.runtime.node_source_watermarks import (
    build_dbt_node_source_watermark_context,
    record_dbt_successful_node_source_watermark,
    write_dbt_node_source_watermark_records,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCommandExecutionResult,
    DbtDeferClonePlan,
    DbtDeferClonePrephaseContext,
    DbtExecutionOutcome,
    DbtInteropCompiledProject,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlan,
    DbtModelPlanningResult,
    DbtNodeExecutionResult,
    DbtPlanEnvironment,
    DbtPlannedWork,
    DbtPreExecutionOutputs,
    DbtSqlbuildPlanArtifacts,
    DbtSqlbuildPlanRequest,
    DbtSqlbuildReplanResult,
    DbtTrackedExecution,
    DbtWriteIdentities,
)
from sqlbuild.integrations.dbt.pipeline.helpers.defer_clone import (
    resolve_dbt_defer_clone_from,
    resolve_defer_clone_unique_ids,
    resolve_defer_clone_view_chain_terms,
    resolve_defer_clone_view_chain_unique_ids,
    run_dbt_defer_clone_prephase,
)
from sqlbuild.integrations.dbt.pipeline.helpers.defer_clone_progress import (
    run_dbt_defer_clone_view_chain_prephase,
    selected_dbt_defer_clone_cause_names,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import (
    append_manifest_seed_warnings,
    append_stale_out_of_selection_warning,
    build_dbt_non_model_run_unique_ids,
    build_dbt_pruned_seed_unique_ids,
    build_dbt_pruned_test_unique_ids,
    build_deferred_dbt_relations,
    dbt_blocked_exit_code,
    execute_dbt_commands,
    render_dbt_execution_summary_footer,
)
from sqlbuild.integrations.dbt.pipeline.helpers.missing_relations import (
    find_and_report_missing_dbt_relation_blocks,
    missing_dbt_relations_exit_code,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import (
    build_dbt_model_plan_output,
    build_sqlbuild_plan_output,
)
from sqlbuild.integrations.dbt.pipeline.helpers.source_freshness import (
    append_dbt_source_freshness_records,
)
from sqlbuild.integrations.dbt.pipeline.main.render_plan import render_dbt_interop_plan
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.integrations.dbt.shared.helpers.progress import report_progress
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
    DbtInteropSkipReason,
    DbtInteropSqlbuildTestAction,
)
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.helpers.output.display import DisplayOptions
from sqlbuild.shared.models import ConnectionHooks


def resolve_dbt_planned_work(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    plan: DbtInteropPlan,
) -> DbtPlannedWork:
    """Attach dbt model planning and warnings and resolve the connection config."""

    connection_progress: Any = build_connection_progress_reporter(
        adapter_name=compiled.adapter_name,
        stream=invocation.output_stream,
        use_color=request.use_color,
    )
    dbt_model_plan: DbtModelPlanningResult | None = build_dbt_model_plan_output(
        environment=DbtPlanEnvironment(
            project_dir=request.project_dir,
            discovered_inputs=invocation.discovered_inputs,
            project=compiled.project,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
        ),
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
        full_refresh="--full-refresh" in invocation.routed.dbt_args,
        force=invocation.effective_force,
        hooks=ConnectionHooks(
            on_progress=request.on_progress,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
        ),
    )
    if dbt_model_plan is not None:
        plan = replace(plan, dbt_model_plan=dbt_model_plan)
        plan = append_stale_out_of_selection_warning(plan=plan, dbt_model_plan=dbt_model_plan)
    plan = append_manifest_seed_warnings(plan=plan, manifest=manifest)
    plan = replace(
        plan,
        dbt_non_model_run_unique_ids=build_dbt_non_model_run_unique_ids(
            command=request.command,
            plan=plan,
        ),
        dbt_pruned_seed_unique_ids=build_dbt_pruned_seed_unique_ids(
            command=request.command,
            plan=plan,
        ),
        dbt_pruned_test_unique_ids=build_dbt_pruned_test_unique_ids(
            command=request.command,
            plan=plan,
        ),
    )
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(
            discovered_inputs=invocation.discovered_inputs
        ),
        project_dir=request.project_dir,
        adapter_name=compiled.adapter_name,
        discovered_inputs=invocation.discovered_inputs,
    )
    return DbtPlannedWork(plan=plan, connection_config=connection_config)


def build_dbt_write_identities(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    plan: DbtInteropPlan,
) -> DbtWriteIdentities:
    """Build identity hashes and query SQL lookups used for dbt state writes."""

    expected_version_hash_by_unique_id: dict[str, str | None] = (
        build_expected_dbt_model_version_hashes(manifest=manifest, graph=graph)
    )
    previous_version_hash_by_unique_id: dict[str, str] = {
        entry.unique_id: entry.previous_version_hash
        for entry in (plan.dbt_model_plan.entries if plan.dbt_model_plan is not None else ())
        if entry.previous_version_hash is not None
    }
    write_identity_hashes: dict[GraphNodeKey, str] = build_dbt_write_identity_hashes(
        manifest=manifest,
        graph=graph,
        run_unique_ids=frozenset(
            plan.dbt_model_plan.run_unique_ids if plan.dbt_model_plan is not None else ()
        ),
        expected_version_hash_by_unique_id=expected_version_hash_by_unique_id,
        previous_version_hash_by_unique_id=previous_version_hash_by_unique_id,
    )
    return DbtWriteIdentities(
        expected_version_hash_by_unique_id=expected_version_hash_by_unique_id,
        seed_identity_by_unique_id={
            unique_id: seed.identity_hash
            for unique_id, seed in manifest.seeds_by_unique_id.items()
            if seed.identity_hash is not None
        },
        previous_version_hash_by_unique_id=previous_version_hash_by_unique_id,
        write_identity_hashes=write_identity_hashes,
        query_sql_by_unique_id={
            unique_id: model.query_sql for unique_id, model in manifest.models_by_unique_id.items()
        },
    )


def resolve_dbt_defer_clone_plan(
    *,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    plan: DbtInteropPlan,
) -> DbtDeferClonePlan:
    """Resolve defer-clone selection, causes, and view-chain unique ids."""

    enabled: bool = resolve_dbt_defer_clone_from(
        cli_defer_clone_from=invocation.routed.defer_clone_from,
        project_defer_clone_from=(invocation.discovered_inputs.project_config.dbt.defer_clone_from),
        local_defer_clone_from=invocation.discovered_inputs.local_config.dbt.defer_clone_from,
    )
    if not enabled:
        return DbtDeferClonePlan(
            enabled=False,
            unique_ids=frozenset(),
            cause_names=(),
            view_chain_terms=(),
            view_chain_unique_ids=frozenset(),
        )
    return DbtDeferClonePlan(
        enabled=True,
        unique_ids=resolve_defer_clone_unique_ids(
            graph=graph,
            manifest=manifest,
            project=compiled.project,
            selected_sqlbuild_model_names=plan.selection.sqlbuild_model_names,
            selected_dbt_unique_ids=plan.dbt_selected_unique_ids,
            required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
        ),
        cause_names=selected_dbt_defer_clone_cause_names(
            manifest=manifest,
            selected_sqlbuild_model_names=plan.selection.sqlbuild_model_names,
            selected_dbt_unique_ids=plan.dbt_selected_unique_ids,
        ),
        view_chain_terms=resolve_defer_clone_view_chain_terms(
            graph=graph,
            manifest=manifest,
            project=compiled.project,
            selected_sqlbuild_model_names=plan.selection.sqlbuild_model_names,
            selected_dbt_unique_ids=plan.dbt_selected_unique_ids,
        ),
        view_chain_unique_ids=resolve_defer_clone_view_chain_unique_ids(
            graph=graph,
            manifest=manifest,
            project=compiled.project,
            selected_sqlbuild_model_names=plan.selection.sqlbuild_model_names,
            selected_dbt_unique_ids=plan.dbt_selected_unique_ids,
        ),
    )


def resolve_dbt_pre_execution_outputs(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    plan: DbtInteropPlan,
    defer_clone: DbtDeferClonePlan,
    merged_dbt_argv: tuple[str, ...] | None,
) -> DbtPreExecutionOutputs:
    """Resolve missing-relation blocks and the pre-execution SQLBuild plan output."""

    missing_relation_blocked_models: dict[str, tuple[DbtManifestModel, ...]] = {}
    if merged_dbt_argv is not None or plan.sqlbuild_skip_reason is not None:
        return DbtPreExecutionOutputs(
            plan=plan,
            missing_relation_blocked_models=missing_relation_blocked_models,
        )
    missing_relation_blocked_models = find_and_report_missing_dbt_relation_blocks(
        project_dir=request.project_dir,
        discovered_inputs=invocation.discovered_inputs,
        project=compiled.project,
        manifest=manifest,
        adapter=compiled.adapter,
        adapter_name=compiled.adapter_name,
        selected_model_names=plan.selection.sqlbuild_model_names,
        dbt_unique_ids_selected_for_execution=frozenset(
            (
                *plan.dbt_selected_unique_ids,
                *plan.selection.dbt_required_unique_ids,
                *defer_clone.unique_ids,
                *defer_clone.view_chain_unique_ids,
            )
        ),
        output_stream=invocation.output_stream,
    )
    connection_progress: Any = build_connection_progress_reporter(
        adapter_name=compiled.adapter_name,
        stream=invocation.output_stream,
        use_color=request.use_color,
    )
    sqlbuild_plan_output: PlanOutput | None = build_sqlbuild_plan_output(
        environment=DbtPlanEnvironment(
            project_dir=request.project_dir,
            discovered_inputs=invocation.discovered_inputs,
            project=compiled.project,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
        ),
        request=DbtSqlbuildPlanRequest(
            selected_model_names=plan.selection.sqlbuild_model_names,
            required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
            sqlbuild_args=invocation.effective_sqlbuild_args,
            external_blocked_model_names=(
                *(
                    plan.dbt_model_plan.blocked_sqlbuild_model_names
                    if plan.dbt_model_plan is not None
                    else ()
                ),
                *missing_relation_blocked_models,
            ),
            deferred_relations=build_deferred_dbt_relations(plan=plan, manifest=manifest),
            dependency_baseline_entries=(),
            disable_scope_pruning=request.command == DbtInteropCommand.TEST,
            artifacts=DbtSqlbuildPlanArtifacts(
                manifest=manifest if request.command == DbtInteropCommand.TEST else None,
                dbt_manifest=manifest,
                dbt_graph=graph,
                dbt_source_freshness=(
                    plan.dbt_model_plan.source_freshness
                    if plan.dbt_model_plan is not None
                    else None
                ),
            ),
        ),
        hooks=ConnectionHooks(
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
        ),
    )
    if sqlbuild_plan_output is not None:
        plan = replace(plan, sqlbuild_plan_output=sqlbuild_plan_output)
    return DbtPreExecutionOutputs(
        plan=plan,
        missing_relation_blocked_models=missing_relation_blocked_models,
    )


def write_dbt_execution_plan_text(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    plan: DbtInteropPlan,
    merged_dbt_argv: tuple[str, ...] | None,
) -> None:
    """Render and write the interop plan to the output stream for text mode."""

    if request.json_output:
        return
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
        use_color=request.use_color,
        display_options=DisplayOptions(max_entries_per_section=None if request.verbose else 10),
    )
    invocation.output_stream.write(rendered_plan + "\n\n")
    invocation.output_stream.flush()


def run_dbt_defer_clone_prephases(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    plan: DbtInteropPlan,
    defer_clone: DbtDeferClonePlan,
    connection_config: dict[str, object],
) -> int | None:
    """Run defer-clone prephases and return a failing exit code when one fails."""

    if defer_clone.enabled:
        _ = run_dbt_defer_clone_prephase(
            context=DbtDeferClonePrephaseContext(
                project_dir=request.project_dir,
                discovered_inputs=invocation.discovered_inputs,
                dbt_options=invocation.dbt_options,
                runner=invocation.runner,
                adapter=compiled.adapter,
                project=compiled.project,
                connection_config=connection_config,
            ),
            current_manifest=manifest,
            unique_ids=tuple(sorted(defer_clone.unique_ids)),
            on_progress=request.on_progress,
            output_stream=invocation.output_stream,
            use_color=request.use_color,
            caused_by_names=defer_clone.cause_names,
        )
    if defer_clone.view_chain_terms:
        view_chain_execution: DbtCommandExecutionResult = run_dbt_defer_clone_view_chain_prephase(
            dbt_options=invocation.dbt_options,
            dbt_executable=plan.dbt_command_argv[0],
            view_chain_terms=defer_clone.view_chain_terms,
            view_chain_unique_ids=defer_clone.view_chain_unique_ids,
            caused_by_names=defer_clone.cause_names,
            output_stream=invocation.output_stream,
            use_color=request.use_color,
            on_progress=request.on_progress,
        )
        if view_chain_execution.returncode != 0:
            return view_chain_execution.returncode
    if defer_clone.enabled or defer_clone.view_chain_terms:
        invocation.output_stream.write("\n")
        invocation.output_stream.flush()
    return None


def execute_dbt_with_state_tracking(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    plan: DbtInteropPlan,
    identities: DbtWriteIdentities,
    merged_dbt_argv: tuple[str, ...] | None,
    connection_config: dict[str, object],
) -> DbtTrackedExecution:
    """Execute dbt while recording fingerprints and node source watermarks."""

    watermark_context: NodeSourceWatermarkExecutionContext | None = _prepare_dbt_watermark_context(
        request=request,
        compiled=compiled,
        manifest=manifest,
        graph=graph,
        plan=plan,
        connection_config=connection_config,
    )
    fingerprint_warnings: list[str] = []
    buffered_results: list[DbtNodeExecutionResult] = []
    state_connection: object | None = None
    query_change_tracking: bool = compiled.project.settings.query_change_tracking
    if query_change_tracking and compiled.adapter_name != BuiltinAdapter.DUCKDB:
        state_connect_start: float = time.monotonic()
        report_progress(
            request.on_progress, "Connecting to warehouse for dbt fingerprint writes..."
        )
        state_connection = compiled.adapter.connect(connection_config)
        report_progress(
            request.on_progress,
            "Connected for dbt fingerprint writes. "
            f"({time.monotonic() - state_connect_start:.2f}s)",
        )

    def record_dbt_node_result(result: DbtNodeExecutionResult) -> None:
        record_dbt_successful_node_source_watermark(
            context=watermark_context,
            result=result,
            manifest=manifest,
            run_id=compiled.project.run_id,
            node_version_hash=identities.write_identity_hashes.get(
                dbt_graph_node_key(result.unique_id)
            ),
        )
        if not query_change_tracking:
            return
        if compiled.adapter_name == BuiltinAdapter.DUCKDB:
            buffered_results.append(result)
            return
        if state_connection is None:
            return
        _ = try_write_dbt_node_fingerprint(
            result=result,
            adapter=compiled.adapter,
            connection=state_connection,
            destination=build_dbt_fingerprint_destination(compiled.project),
            warnings=fingerprint_warnings,
            query_sql=identities.query_sql_by_unique_id.get(result.unique_id),
            seed_identity_hash=identities.seed_identity_by_unique_id.get(result.unique_id),
            version_hash_override=identities.write_identity_hashes.get(
                dbt_graph_node_key(result.unique_id)
            ),
        )

    try:
        execution: DbtCommandExecutionResult = execute_dbt_commands(
            runner=invocation.runner,
            options=invocation.dbt_options,
            merged_argv=merged_dbt_argv,
            progress_stream=invocation.output_stream,
            stdout_stream=invocation.dbt_output_stream,
            stderr_stream=invocation.output_stream,
            use_color=request.use_color,
            skip_message=(
                "Skipping dbt tests: no dbt tests for the selection."
                if request.command == DbtInteropCommand.TEST
                else "Skipping dbt: no dbt work selected."
            ),
            on_node_result=record_dbt_node_result,
            on_progress=request.on_progress,
        )
    finally:
        if state_connection is not None:
            compiled.adapter.close(state_connection)

    if buffered_results and query_change_tracking:
        write_buffered_dbt_fingerprints(
            request=request,
            compiled=compiled,
            identities=identities,
            connection_config=connection_config,
            buffered_results=tuple(buffered_results),
            fingerprint_warnings=fingerprint_warnings,
        )
    if execution.returncode == 0 and watermark_context is not None:
        watermark_start: float = time.monotonic()
        report_progress(request.on_progress, "Recording dbt node source watermarks...")
        watermark_connection: object = compiled.adapter.connect(connection_config)
        try:
            write_dbt_node_source_watermark_records(
                context=watermark_context,
                adapter=compiled.adapter,
                connection=watermark_connection,
                state_database=compiled.project.effective_target_database,
                state_schema=compiled.project.effective_target_schema,
            )
        finally:
            compiled.adapter.close(watermark_connection)
        report_progress(
            request.on_progress,
            f"Recorded dbt node source watermarks. ({time.monotonic() - watermark_start:.2f}s)",
        )
    return DbtTrackedExecution(
        execution=execution,
        fingerprint_warnings=tuple(fingerprint_warnings),
    )


def write_buffered_dbt_fingerprints(
    *,
    request: DbtInteropExecutionRequest,
    compiled: DbtInteropCompiledProject,
    identities: DbtWriteIdentities,
    connection_config: dict[str, object],
    buffered_results: tuple[DbtNodeExecutionResult, ...],
    fingerprint_warnings: list[str],
) -> None:
    """Write buffered dbt fingerprints on a fresh connection after execution."""

    fingerprint_start: float = time.monotonic()
    report_progress(request.on_progress, "Recording dbt fingerprints...")
    connection: object = compiled.adapter.connect(connection_config)
    try:
        dbt_result: DbtNodeExecutionResult
        for dbt_result in buffered_results:
            _ = try_write_dbt_node_fingerprint(
                result=dbt_result,
                adapter=compiled.adapter,
                connection=connection,
                destination=build_dbt_fingerprint_destination(compiled.project),
                warnings=fingerprint_warnings,
                query_sql=identities.query_sql_by_unique_id.get(dbt_result.unique_id),
                seed_identity_hash=identities.seed_identity_by_unique_id.get(dbt_result.unique_id),
                version_hash_override=identities.write_identity_hashes.get(
                    dbt_graph_node_key(dbt_result.unique_id)
                ),
            )
    finally:
        compiled.adapter.close(connection)
    report_progress(
        request.on_progress,
        f"Recorded dbt fingerprints. ({time.monotonic() - fingerprint_start:.2f}s)",
    )


def write_dbt_execution_summary(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    tracked: DbtTrackedExecution,
) -> None:
    """Write fingerprint warnings and the dbt execution summary footer."""

    style: CliStyle = CliStyle(use_color=request.use_color)
    warning: str
    for warning in tracked.fingerprint_warnings:
        invocation.output_stream.write(style.warning(f"Warning: {warning}") + "\n")
    if tracked.fingerprint_warnings:
        invocation.output_stream.flush()
    summary_footer: str | None = render_dbt_execution_summary_footer(
        node_results=tracked.execution.node_results,
        use_color=request.use_color,
    )
    if summary_footer is not None:
        invocation.output_stream.write("\n" + summary_footer + "\n")
        invocation.output_stream.flush()


def _prepare_dbt_watermark_context(
    *,
    request: DbtInteropExecutionRequest,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    plan: DbtInteropPlan,
    connection_config: dict[str, object],
) -> NodeSourceWatermarkExecutionContext | None:
    """Read the node source watermark context when dbt planned source freshness."""

    if (
        plan.dbt_model_plan is None
        or plan.dbt_model_plan.source_freshness is None
        or not plan.dbt_model_plan.source_freshness.observed_records
    ):
        return None
    watermark_connect_start: float = time.monotonic()
    report_progress(request.on_progress, "Reading dbt node source watermarks...")
    connection: object = compiled.adapter.connect(connection_config)
    try:
        watermark_context: NodeSourceWatermarkExecutionContext | None = (
            build_dbt_node_source_watermark_context(
                manifest=manifest,
                graph=graph,
                source_records=plan.dbt_model_plan.source_freshness.observed_records,
                adapter=compiled.adapter,
                connection=connection,
                state_database=compiled.project.effective_target_database,
                state_schema=compiled.project.effective_target_schema,
            )
        )
    finally:
        compiled.adapter.close(connection)
    report_progress(
        request.on_progress,
        f"Read dbt node source watermarks. ({time.monotonic() - watermark_connect_start:.2f}s)",
    )
    return watermark_context


def resolve_sqlbuild_execution_plan_output(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    pre_execution: DbtPreExecutionOutputs,
    outcome: DbtExecutionOutcome,
    defer_clone: DbtDeferClonePlan,
    merged_dbt_argv: tuple[str, ...] | None,
) -> DbtSqlbuildReplanResult:
    """Resolve the post-dbt SQLBuild plan output, replanning after dbt execution."""

    invocation.output_stream.write("\n")
    invocation.output_stream.flush()
    plan: DbtInteropPlan = pre_execution.plan
    plan_output: PlanOutput | None = plan.sqlbuild_plan_output
    missing_relation_blocked_models: dict[str, tuple[DbtManifestModel, ...]] = (
        pre_execution.missing_relation_blocked_models
    )
    if plan_output is not None and merged_dbt_argv is None:
        return DbtSqlbuildReplanResult(
            plan_output=plan_output,
            missing_relation_blocked_models=missing_relation_blocked_models,
        )
    missing_relation_blocked_models = find_and_report_missing_dbt_relation_blocks(
        project_dir=request.project_dir,
        discovered_inputs=invocation.discovered_inputs,
        project=compiled.project,
        manifest=manifest,
        adapter=compiled.adapter,
        adapter_name=compiled.adapter_name,
        selected_model_names=plan.selection.sqlbuild_model_names,
        dbt_unique_ids_selected_for_execution=frozenset(
            (
                *plan.dbt_selected_unique_ids,
                *plan.selection.dbt_required_unique_ids,
                *defer_clone.unique_ids,
                *defer_clone.view_chain_unique_ids,
            )
        ),
        output_stream=invocation.output_stream,
    )
    connection_progress: Any = build_connection_progress_reporter(
        adapter_name=compiled.adapter_name,
        stream=invocation.output_stream,
        blank_line_after_complete=True,
        use_color=request.use_color,
    )
    plan_output = build_sqlbuild_plan_output(
        environment=DbtPlanEnvironment(
            project_dir=request.project_dir,
            discovered_inputs=invocation.discovered_inputs,
            project=compiled.project,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
        ),
        request=DbtSqlbuildPlanRequest(
            selected_model_names=plan.selection.sqlbuild_model_names,
            required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
            sqlbuild_args=invocation.effective_sqlbuild_args,
            forced_stale_model_names=outcome.stale_sqlbuild_model_names,
            external_blocked_model_names=(
                *outcome.blocked_sqlbuild_model_names,
                *missing_relation_blocked_models,
            ),
            deferred_relations=build_deferred_dbt_relations(plan=plan, manifest=manifest),
            dependency_baseline_entries=(),
            disable_scope_pruning=request.command == DbtInteropCommand.TEST,
            artifacts=DbtSqlbuildPlanArtifacts(
                manifest=manifest if request.command == DbtInteropCommand.TEST else None,
                dbt_manifest=manifest,
                dbt_graph=graph,
                dbt_source_freshness=(
                    plan.dbt_model_plan.source_freshness
                    if plan.dbt_model_plan is not None
                    else None
                ),
            ),
        ),
        hooks=ConnectionHooks(
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
        ),
    )
    return DbtSqlbuildReplanResult(
        plan_output=plan_output,
        missing_relation_blocked_models=missing_relation_blocked_models,
    )


def run_dbt_sqlbuild_work(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    plan_output: PlanOutput,
    connection_config: dict[str, object],
) -> int:
    """Execute the SQLBuild portion of the interop plan and return its exit code."""

    actions: tuple[DbtInteropSqlbuildTestAction, ...] = ()
    if request.command == DbtInteropCommand.TEST:
        actions = resolve_sqlbuild_test_actions(select=invocation.routed.select)
    return execute_dbt_sqlbuild_work(
        context=DbtSqlbuildWorkContext(
            plan_output=plan_output,
            connection_config=connection_config,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
            output_stream=invocation.output_stream,
            use_color=request.use_color,
        ),
        command=request.command,
        project=compiled.project,
        project_dir=request.project_dir,
        fail_fast=request.fail_fast,
        verbose=request.verbose,
        actions=actions,
    )


def write_sqlbuild_skip_notice(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    skip_reason_message: str | None,
    current_message: str | None,
) -> None:
    """Write the skip transition output before resolving the final exit code."""

    if skip_reason_message is not None:
        invocation.output_stream.write("\n")
        invocation.output_stream.flush()
        report_progress(request.on_progress, skip_reason_message)
    if current_message is not None:
        style: CliStyle = CliStyle(use_color=request.use_color)
        invocation.output_stream.write(style.muted(current_message) + "\n")
        invocation.output_stream.flush()


def finalize_dbt_interop_exit(
    *,
    request: DbtInteropExecutionRequest,
    compiled: DbtInteropCompiledProject,
    plan: DbtInteropPlan,
    connection_config: dict[str, object],
    dbt_returncode: int,
    missing_relation_blocked_models: dict[str, tuple[DbtManifestModel, ...]],
    always_append_freshness: bool = False,
) -> int:
    """Resolve the final exit code and append source freshness records on success."""

    exit_code: int = max(
        dbt_returncode,
        dbt_blocked_exit_code(plan),
        missing_dbt_relations_exit_code(missing_relation_blocked_models),
    )
    if exit_code == 0 or always_append_freshness:
        append_dbt_source_freshness_records(
            plan=plan,
            adapter=compiled.adapter,
            connection_config=connection_config,
            project=compiled.project,
            on_progress=request.on_progress,
        )
    return exit_code
