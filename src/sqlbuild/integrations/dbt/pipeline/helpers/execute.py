"""Execution helpers for dbt interop pipelines."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TextIO, cast

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.helpers.cli.runner import (
    DbtRunner,
    build_dbt_command_argv,
    parse_dbt_ls_json_lines,
)
from sqlbuild.integrations.dbt.helpers.planning.model_planning import (
    build_downstream_sqlbuild_model_names,
)
from sqlbuild.integrations.dbt.helpers.runtime.event_stream import (
    execute_dbt_json_event_stream,
    render_dbt_node_result,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandExecutionResult,
    DbtCommandResult,
    DbtExecutionOutcome,
    DbtInteropPlan,
    DbtLsNode,
    DbtModelExecutionOutcomeEntry,
    DbtModelPlanEntry,
    DbtModelPlanningResult,
    DbtNodeExecutionResult,
    DbtNodeMessage,
)
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
    DbtModelOutcomeState,
    DbtModelPlanAction,
    DbtSupportedResourceType,
)
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.status import TransientStatusReporter
from sqlbuild.shared.helpers.summary_footer import format_summary_footer

_DBT_SUCCESS_STATUSES: frozenset[str] = frozenset(
    {"ok", "success", "pass", "passed", "warn", "warning"}
)
_DBT_WARN_STATUSES: frozenset[str] = frozenset({"warn", "warning"})
_DBT_FAIL_STATUSES: frozenset[str] = frozenset({"error", "fail", "failed"})
_DBT_SKIP_STATUSES: frozenset[str] = frozenset({"skip", "skipped"})


def execute_dbt_commands(
    *,
    runner: DbtRunner,
    options: DbtCliOptions,
    merged_argv: tuple[str, ...] | None,
    progress_stream: TextIO,
    stdout_stream: TextIO,
    stderr_stream: TextIO,
    use_color: bool,
    skip_message: str = "Skipping dbt: no dbt work selected.",
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> DbtCommandExecutionResult:
    """Execute the merged dbt command, or skip when no dbt work exists."""

    if merged_argv is None:
        style: CliStyle = CliStyle(use_color=use_color)
        progress_stream.write(style.muted(skip_message) + "\n")
        progress_stream.flush()
        return DbtCommandExecutionResult(returncode=0)
    argv: tuple[str, ...] = merged_argv
    style: CliStyle = CliStyle(use_color=use_color)
    dbt_execution_label: str = style.dbt_execution_label("dbt execution")
    dbt_command_name: str = Path(argv[0]).name
    dbt_execution_detail_text: str = (
        f"{dbt_command_name} {argv[1]}" if len(argv) >= 2 else dbt_command_name
    )
    dbt_execution_detail: str = style.muted(dbt_execution_detail_text)
    progress_stream.write(f"{dbt_execution_label}  {dbt_execution_detail}\n\n")
    progress_stream.flush()
    expected_total: int | None = _dbt_execution_expected_total(
        runner=runner,
        options=options,
        argv=argv,
        stream=progress_stream,
        use_color=use_color,
    )
    returncode: int
    results: tuple[DbtNodeExecutionResult, ...]
    returncode, results = execute_dbt_json_event_stream(
        argv=argv,
        cwd=options.project_dir,
        stream=stdout_stream,
        use_color=use_color,
        target_path=options.target_path,
        display_total=expected_total,
        on_node_result=on_node_result,
    )
    if on_progress is not None:
        on_progress("Finalizing dbt run...")
    streamed_result_count: int = len(results)
    results = _append_missing_run_results(
        results=results,
        target_path=options.target_path,
    )
    for offset, result in enumerate(results[streamed_result_count:], start=1):
        render_dbt_node_result(
            stream=stdout_stream,
            style=style,
            result=result,
            display_index=streamed_result_count + offset,
            display_total=(expected_total if expected_total is not None else len(results)),
        )
        if on_node_result is not None:
            on_node_result(result)
    if on_progress is not None:
        on_progress("Finalized dbt run.")
    del runner, stderr_stream
    return DbtCommandExecutionResult(returncode=returncode, node_results=results)


def _dbt_execution_expected_total(
    *,
    runner: DbtRunner,
    options: DbtCliOptions,
    argv: tuple[str, ...],
    stream: TextIO,
    use_color: bool,
) -> int | None:
    ls_argv: tuple[str, ...] | None = _dbt_ls_argv_from_execution_argv(argv)
    if ls_argv is None:
        return None
    status: TransientStatusReporter | None = _start_dbt_execution_selection_status(
        stream=stream,
        use_color=use_color,
    )
    start: float = time.monotonic()
    try:
        result: DbtCommandResult = runner.invoke(argv=ls_argv, cwd=options.project_dir)
    finally:
        if status is not None:
            status.complete(f"Resolved dbt execution selection. ({time.monotonic() - start:.2f}s)")
    if result.returncode != 0:
        return None
    return len(parse_dbt_ls_json_lines(stdout=result.stdout))


def _start_dbt_execution_selection_status(
    *, stream: TextIO, use_color: bool
) -> TransientStatusReporter | None:
    status: TransientStatusReporter = TransientStatusReporter(stream=stream, use_color=use_color)
    status.start("Resolving dbt execution selection...")
    return status


def _dbt_ls_argv_from_execution_argv(argv: tuple[str, ...]) -> tuple[str, ...] | None:
    if len(argv) < 2:
        return None
    execution_only_flags: frozenset[str] = frozenset({"--full-refresh", "--fail-fast"})
    converted: list[str] = [argv[0], "ls", "--output", "json"]
    for arg in argv[2:]:
        if arg in execution_only_flags:
            continue
        converted.append(arg)
    return tuple(converted)


def render_dbt_execution_summary_footer(
    *,
    node_results: tuple[DbtNodeExecutionResult, ...],
    use_color: bool,
) -> str | None:
    """Render a PASS/WARN/FAIL/SKIP/TOTAL footer for executed dbt nodes."""

    if not node_results:
        return None
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    elapsed: float = 0.0
    node_result: DbtNodeExecutionResult
    for node_result in node_results:
        status: str = node_result.status.lower()
        if node_result.execution_time is not None:
            elapsed += node_result.execution_time
        if status in _DBT_WARN_STATUSES:
            warn_count += 1
        elif status in _DBT_FAIL_STATUSES:
            fail_count += 1
        elif status in _DBT_SKIP_STATUSES:
            skip_count += 1
        elif status in _DBT_SUCCESS_STATUSES:
            pass_count += 1
    total_count: int = pass_count + warn_count + fail_count + skip_count
    style: CliStyle = CliStyle(use_color=use_color)
    if fail_count > 0:
        status_line: str = style.error("Completed with errors.")
    elif warn_count > 0:
        status_line = style.warning("Completed with warnings.")
    else:
        status_line = style.success("Completed successfully.")
    counts_line: str = format_summary_footer(
        counts=(
            ("PASS", pass_count),
            ("WARN", warn_count),
            ("FAIL", fail_count),
            ("SKIP", skip_count),
            ("TOTAL", total_count),
        ),
        use_color=use_color,
        elapsed=f"{elapsed:.2f}s",
    )
    return f"{status_line}\n{counts_line}"


def build_dbt_execution_outcome(
    *,
    plan: DbtInteropPlan,
    graph: DbtCombinedGraph,
    node_results: tuple[DbtNodeExecutionResult, ...],
) -> DbtExecutionOutcome:
    """Build a SQLBuild-facing dbt model outcome overlay."""

    if plan.dbt_model_plan is None:
        return DbtExecutionOutcome()
    planned_entries: dict[str, DbtModelPlanEntry] = {
        entry.unique_id: entry for entry in plan.dbt_model_plan.entries
    }
    entries_by_unique_id: dict[str, DbtModelExecutionOutcomeEntry] = {}
    for entry in plan.dbt_model_plan.entries:
        if entry.action == DbtModelPlanAction.CURRENT:
            entries_by_unique_id[entry.unique_id] = DbtModelExecutionOutcomeEntry(
                unique_id=entry.unique_id,
                state=DbtModelOutcomeState.CURRENT,
                planned_action=entry.action,
                relation_name=entry.relation_name,
                node_checksum=entry.expected_version_hash,
            )
        elif entry.action == DbtModelPlanAction.BLOCKED:
            entries_by_unique_id[entry.unique_id] = DbtModelExecutionOutcomeEntry(
                unique_id=entry.unique_id,
                state=DbtModelOutcomeState.BLOCKING,
                planned_action=entry.action,
                status=entry.reason.value,
                relation_name=entry.relation_name,
                node_checksum=entry.expected_version_hash,
            )
    result: DbtNodeExecutionResult
    for result in node_results:
        if result.resource_type != DbtSupportedResourceType.MODEL:
            continue
        planned_entry: DbtModelPlanEntry | None = planned_entries.get(result.unique_id)
        planned_action: DbtModelPlanAction | None = (
            planned_entry.action if planned_entry is not None else None
        )
        state: DbtModelOutcomeState = _outcome_state_for_result(
            result=result,
            planned_action=planned_action,
        )
        entries_by_unique_id[result.unique_id] = DbtModelExecutionOutcomeEntry(
            unique_id=result.unique_id,
            state=state,
            planned_action=planned_action,
            status=result.status,
            relation_name=(
                result.relation_name
                or (planned_entry.relation_name if planned_entry is not None else None)
            ),
            node_checksum=(
                result.node_checksum
                or (planned_entry.expected_version_hash if planned_entry is not None else None)
            ),
            messages=result.messages,
        )
    entries: tuple[DbtModelExecutionOutcomeEntry, ...] = tuple(
        entries_by_unique_id[unique_id] for unique_id in sorted(entries_by_unique_id)
    )
    return DbtExecutionOutcome(
        entries=entries,
        stale_sqlbuild_model_names=build_downstream_sqlbuild_model_names(
            graph=graph,
            dbt_unique_ids=tuple(
                entry.unique_id for entry in entries if entry.state == DbtModelOutcomeState.CHANGED
            ),
        ),
        blocked_sqlbuild_model_names=build_downstream_sqlbuild_model_names(
            graph=graph,
            dbt_unique_ids=tuple(
                entry.unique_id for entry in entries if entry.state == DbtModelOutcomeState.BLOCKING
            ),
        ),
    )


def _outcome_state_for_result(
    *, result: DbtNodeExecutionResult, planned_action: DbtModelPlanAction | None
) -> DbtModelOutcomeState:
    normalized_status: str = result.status.lower()
    if normalized_status not in _DBT_SUCCESS_STATUSES:
        return DbtModelOutcomeState.BLOCKING
    if planned_action == DbtModelPlanAction.RUN:
        return DbtModelOutcomeState.CHANGED
    return DbtModelOutcomeState.CURRENT


def _append_missing_run_results(
    *, results: tuple[DbtNodeExecutionResult, ...], target_path: Path | None
) -> tuple[DbtNodeExecutionResult, ...]:
    if target_path is None:
        return results
    run_results_path: Path = target_path / "run_results.json"
    if not run_results_path.exists():
        return results
    existing_unique_ids: frozenset[str] = frozenset(result.unique_id for result in results)
    try:
        payload: object = json.loads(run_results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return results
    if not isinstance(payload, dict):
        return results
    raw_results: object = payload.get("results")
    if not isinstance(raw_results, list):
        return results
    appended: list[DbtNodeExecutionResult] = list(results)
    total: int = len(raw_results)
    index: int
    raw_result: object
    for index, raw_result in enumerate(raw_results, start=1):
        if not isinstance(raw_result, dict):
            continue
        result_payload: dict[str, object] = cast(dict[str, object], raw_result)
        unique_id: object = result_payload.get("unique_id")
        status: object = result_payload.get("status")
        if not isinstance(unique_id, str) or unique_id in existing_unique_ids:
            continue
        if not isinstance(status, str):
            status = "unknown"
        appended.append(
            DbtNodeExecutionResult(
                unique_id=unique_id,
                resource_type=_resource_type_from_unique_id(unique_id),
                node_name=_node_name_from_unique_id(unique_id),
                status=status,
                index=index,
                total=total,
                execution_time=_execution_time_from_run_result(result_payload),
                messages=_messages_from_run_result(result_payload),
            )
        )
    return tuple(appended)


def _resource_type_from_unique_id(unique_id: str) -> str:
    if "." not in unique_id:
        return "node"
    return unique_id.split(".", 1)[0]


def _node_name_from_unique_id(unique_id: str) -> str:
    if "." not in unique_id:
        return unique_id
    return unique_id.rsplit(".", 1)[-1]


def _execution_time_from_run_result(raw_result: dict[str, object]) -> float | None:
    value: object = raw_result.get("execution_time")
    if isinstance(value, int | float):
        return float(value)
    return None


def _messages_from_run_result(raw_result: dict[str, object]) -> tuple[DbtNodeMessage, ...]:
    message: object = raw_result.get("message")
    if isinstance(message, str) and message.strip():
        return (DbtNodeMessage(level="error", message=message.strip()),)
    failures: object = raw_result.get("failures")
    if isinstance(failures, int) and failures > 0:
        return (DbtNodeMessage(level="error", message=f"{failures} failure(s)"),)
    return ()


def build_merged_dbt_execution_argv(
    *,
    command: DbtInteropCommand,
    options: DbtCliOptions,
    routed_args: tuple[str, ...],
    plan: DbtInteropPlan,
    replay_on_change: str | None = None,
    defer_clone_unique_ids: frozenset[str] = frozenset(),
) -> tuple[str, ...] | None:
    """Build the single dbt argv used for execution."""

    if command == DbtInteropCommand.TEST and not plan.dbt_selected_unique_ids:
        return None
    planned_select_terms: tuple[str, ...] = _planned_dbt_select_terms(
        command=command,
        plan=plan,
        defer_clone_unique_ids=defer_clone_unique_ids,
    )
    if plan.dbt_model_plan is not None:
        if not planned_select_terms:
            return None
        pruned_args: tuple[str, ...] = _replace_dbt_select_terms(
            args=_strip_resolved_dbt_options(routed_args),
            select_terms=planned_select_terms,
        )
        pruned_args = _apply_dbt_replay_on_change(
            args=pruned_args,
            replay_on_change=replay_on_change,
            has_planned_model_work=bool(plan.dbt_model_plan.run_unique_ids),
        )
        return build_dbt_command_argv(
            dbt_executable=plan.dbt_command_argv[0],
            command=command.value,
            options=options,
            args=pruned_args,
        )
    required_selector_terms: tuple[str, ...] = (
        () if defer_clone_unique_ids else plan.dbt_required_selector_terms
    )
    if not plan.dbt_selected_unique_ids and not required_selector_terms:
        return None
    merged_args: tuple[str, ...] = _merge_dbt_select_terms(
        args=_strip_resolved_dbt_options(routed_args),
        extra_terms=required_selector_terms,
    )
    return build_dbt_command_argv(
        dbt_executable=plan.dbt_command_argv[0],
        command=command.value,
        options=options,
        args=merged_args,
    )


def _apply_dbt_replay_on_change(
    *, args: tuple[str, ...], replay_on_change: str | None, has_planned_model_work: bool
) -> tuple[str, ...]:
    policy: str | None = replay_on_change.strip().lower() if replay_on_change is not None else None
    if policy in (None, "", "forward_only"):
        return args
    if policy != "full":
        raise DbtInteropConfigError(
            "[dbt].replay_on_change must be 'forward_only' or 'full'; "
            "bounded replay policies are not supported for dbt"
        )
    if not has_planned_model_work or "--full-refresh" in args:
        return args
    return ("--full-refresh", *args)


def build_deferred_dbt_relations(
    *, plan: DbtInteropPlan, manifest: DbtManifestIndex
) -> dict[str, RelationInfo]:
    """Build relation overrides for selected dbt models."""

    relations: dict[str, RelationInfo] = {}
    unique_ids: set[str] = set(plan.selection.dbt_required_unique_ids)
    node: DbtLsNode
    for node in plan.dbt_selected_nodes:
        if node.resource_type == DbtSupportedResourceType.MODEL:
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


def build_dbt_non_model_run_unique_ids(
    *, command: DbtInteropCommand, plan: DbtInteropPlan
) -> tuple[str, ...]:
    """Return non-model dbt selected resources preserved in pruned execution."""

    if plan.dbt_model_plan is None:
        return ()
    seed_unique_ids: tuple[str, ...] = _selected_non_model_unique_ids(
        plan=plan, resource_type=DbtSupportedResourceType.SEED
    )
    test_unique_ids: tuple[str, ...] = _selected_non_model_unique_ids(
        plan=plan, resource_type=DbtSupportedResourceType.TEST
    )
    unit_test_unique_ids: tuple[str, ...] = _selected_non_model_unique_ids(
        plan=plan, resource_type=DbtSupportedResourceType.UNIT_TEST
    )
    if command == DbtInteropCommand.TEST:
        return tuple(sorted(frozenset((*test_unique_ids, *unit_test_unique_ids))))
    if command == DbtInteropCommand.BUILD:
        changed_seed_unique_ids: frozenset[str] = frozenset(seed_unique_ids) & frozenset(
            plan.dbt_model_plan.changed_seed_unique_ids
        )
        if not plan.dbt_model_plan.run_selector_terms:
            return tuple(sorted(changed_seed_unique_ids))
        return tuple(
            sorted(frozenset((*changed_seed_unique_ids, *test_unique_ids, *unit_test_unique_ids)))
        )
    return ()


def build_dbt_pruned_test_unique_ids(
    *, command: DbtInteropCommand, plan: DbtInteropPlan
) -> tuple[str, ...]:
    """Return selected dbt tests pruned from dbt build due to no producer work."""

    if command != DbtInteropCommand.BUILD or plan.dbt_model_plan is None:
        return ()
    if plan.dbt_model_plan.run_selector_terms:
        return ()
    return tuple(
        sorted(
            frozenset(
                (
                    *_selected_non_model_unique_ids(
                        plan=plan, resource_type=DbtSupportedResourceType.TEST
                    ),
                    *_selected_non_model_unique_ids(
                        plan=plan, resource_type=DbtSupportedResourceType.UNIT_TEST
                    ),
                )
            )
        )
    )


def append_stale_out_of_selection_warning(
    *, plan: DbtInteropPlan, dbt_model_plan: DbtModelPlanningResult
) -> DbtInteropPlan:
    """Append a warning when selected models are stale via unselected changed seeds."""

    if dbt_model_plan.stale_out_of_selection_warning_messages:
        return replace(
            plan,
            warnings=(
                *plan.warnings,
                *dbt_model_plan.stale_out_of_selection_warning_messages,
            ),
        )
    stale_seeds: tuple[str, ...] = dbt_model_plan.stale_out_of_selection_seed_unique_ids
    if not stale_seeds:
        return plan
    bullet_lines: str = "\n".join(f"    - {seed.split('.')[-1]}" for seed in stale_seeds)
    warning: str = (
        f"selected models will build on {len(stale_seeds)} stale seed(s) "
        "not selected for rebuild:\n"
        f"{bullet_lines}\n"
        "    rebuild the closure to refresh them: --select +model"
    )
    return replace(plan, warnings=(*plan.warnings, warning))


def append_manifest_seed_warnings(
    *, plan: DbtInteropPlan, manifest: DbtManifestIndex
) -> DbtInteropPlan:
    """Surface manifest-time seed identity warnings (e.g. unreadable seed files)."""

    if not manifest.seed_identity_warnings:
        return plan
    return replace(plan, warnings=(*plan.warnings, *manifest.seed_identity_warnings))


def build_dbt_pruned_seed_unique_ids(
    *, command: DbtInteropCommand, plan: DbtInteropPlan
) -> tuple[str, ...]:
    """Return selected dbt seeds pruned from dbt build due to no producer work."""

    if command != DbtInteropCommand.BUILD or plan.dbt_model_plan is None:
        return ()
    changed: frozenset[str] = frozenset(plan.dbt_model_plan.changed_seed_unique_ids)
    return tuple(
        unique_id
        for unique_id in _selected_non_model_unique_ids(
            plan=plan, resource_type=DbtSupportedResourceType.SEED
        )
        if unique_id not in changed
    )


def build_unblocked_sqlbuild_model_names(plan: DbtInteropPlan) -> tuple[str, ...]:
    """Return selected SQLBuild models not blocked by dbt model planning."""

    if plan.dbt_model_plan is None or not plan.dbt_model_plan.blocked_sqlbuild_model_names:
        return plan.selection.sqlbuild_model_names
    blocked: frozenset[str] = frozenset(plan.dbt_model_plan.blocked_sqlbuild_model_names)
    return tuple(name for name in plan.selection.sqlbuild_model_names if name not in blocked)


def dbt_blocked_exit_code(plan: DbtInteropPlan) -> int:
    """Return non-zero when dbt model planning blocked selected work."""

    if plan.dbt_model_plan is None:
        return 0
    return 1 if plan.dbt_model_plan.blocked_unique_ids else 0


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


def _planned_dbt_select_terms(
    *,
    command: DbtInteropCommand,
    plan: DbtInteropPlan,
    defer_clone_unique_ids: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    if plan.dbt_model_plan is None:
        return ()
    non_model_unique_ids: tuple[str, ...] = build_dbt_non_model_run_unique_ids(
        command=command,
        plan=plan,
    )
    non_model_terms: tuple[str, ...] = _selector_terms_for_unique_ids(
        plan=plan,
        unique_ids=non_model_unique_ids,
    )
    executable_model_unique_ids: frozenset[str] = (
        frozenset((*plan.dbt_selected_unique_ids, *plan.selection.dbt_required_unique_ids))
        - defer_clone_unique_ids
    )
    model_terms: tuple[str, ...] = tuple(
        entry.selector_term
        for entry in plan.dbt_model_plan.entries
        if entry.action == DbtModelPlanAction.RUN and entry.unique_id in executable_model_unique_ids
    )
    return tuple(sorted(frozenset((*model_terms, *non_model_terms))))


def _selected_non_model_unique_ids(
    *, plan: DbtInteropPlan, resource_type: DbtSupportedResourceType
) -> tuple[str, ...]:
    return tuple(
        sorted(
            node.unique_id
            for node in plan.dbt_selected_nodes
            if node.resource_type == resource_type
        )
    )


def _selector_terms_for_unique_ids(
    *, plan: DbtInteropPlan, unique_ids: tuple[str, ...]
) -> tuple[str, ...]:
    unique_id_set: frozenset[str] = frozenset(unique_ids)
    return tuple(
        sorted(
            node.selector_term
            for node in plan.dbt_selected_nodes
            if node.unique_id in unique_id_set
        )
    )


def _replace_dbt_select_terms(
    *, args: tuple[str, ...], select_terms: tuple[str, ...]
) -> tuple[str, ...]:
    stripped: list[str] = []
    index: int = 0
    while index < len(args):
        token: str = args[index]
        if token in {"--select", "--exclude"}:
            index += 1
            while index < len(args) and not args[index].startswith("--"):
                index += 1
            continue
        stripped.append(token)
        index += 1
    return (*stripped, "--select", *select_terms)
