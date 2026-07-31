"""Execution helpers for ordinary dbt interop pipelines."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO, cast

from sqlbuild.integrations.dbt._helpers.graph.core import (
    dbt_model_graph_key,
    expand_combined_downstream,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.constants import (
    DBT_DEFER_FLAG,
    DBT_EXECUTION_FAIL_STATUSES,
    DBT_EXECUTION_SKIP_STATUSES,
    DBT_EXECUTION_SUCCESS_STATUSES,
    DBT_EXECUTION_WARN_STATUSES,
    DBT_SELECT_FLAG,
    DBT_UNIQUE_ID_SEPARATOR,
)
from sqlbuild.integrations.dbt.main.cli._build_command_argv import build_dbt_command_argv
from sqlbuild.integrations.dbt.main.cli._parse_ls_json_lines import parse_dbt_ls_json_lines
from sqlbuild.integrations.dbt.main.runtime._execute_json_event_stream import (
    execute_dbt_json_event_stream,
)
from sqlbuild.integrations.dbt.main.runtime._render_node_result import render_dbt_node_result
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtCommandExecutionResult,
    DbtCommandResult,
    DbtInteropPlan,
    DbtLsNode,
    DbtManifestIndex,
    DbtNodeExecutionResult,
    DbtNodeMessage,
)
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtInteropCommand,
    DbtSupportedResourceType,
)
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.summary_footer import format_summary_footer

_COMMAND_AND_SUBCOMMAND_ARGUMENT_COUNT: int = 2
_DBT_LS_EXCLUDED_EXECUTION_FLAGS: frozenset[str] = frozenset({"--full-refresh", "--fail-fast"})


def execute_dbt_commands(
    *,
    runner: DbtRunner,
    options: DbtCliOptions,
    merged_argv: tuple[str, ...] | None,
    progress_stream: TextIO,
    stdout_stream: TextIO,
    use_color: bool,
    skip_message: str = "Skipping dbt: no dbt work selected.",
    expected_nodes: tuple[DbtLsNode, ...] | None = None,
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
    style = CliStyle(use_color=use_color)
    dbt_command_name: str = Path(argv[0]).name
    command_detail: str = (
        f"{dbt_command_name} {argv[1]}"
        if len(argv) >= _COMMAND_AND_SUBCOMMAND_ARGUMENT_COUNT
        else dbt_command_name
    )
    progress_stream.write(
        f"{style.dbt_execution_label('dbt execution')}  {style.muted(command_detail)}\n\n"
    )
    progress_stream.flush()
    expected_unique_ids: frozenset[str] | None = (
        frozenset(node.unique_id for node in expected_nodes) if expected_nodes is not None else None
    )
    expected_total: int | None = (
        len(expected_unique_ids)
        if expected_unique_ids is not None
        else _dbt_execution_expected_total(
            runner=runner,
            options=options,
            argv=argv,
            stream=progress_stream,
            use_color=use_color,
        )
    )
    target_path: Path | None = _effective_dbt_target_path(options=options)
    returncode: int
    results: tuple[DbtNodeExecutionResult, ...]
    returncode, results = execute_dbt_json_event_stream(
        argv=argv,
        cwd=options.project_dir,
        stream=stdout_stream,
        use_color=use_color,
        target_path=target_path,
        display_total=expected_total,
        on_node_result=on_node_result,
    )
    if on_progress is not None:
        on_progress("Finalizing dbt run...")
    streamed_unique_ids: frozenset[str] = frozenset(result.unique_id for result in results)
    if expected_unique_ids is not None:
        results = tuple(result for result in results if result.unique_id in expected_unique_ids)
    results = _append_missing_run_results(
        results=results,
        target_path=target_path,
        expected_unique_ids=expected_unique_ids,
    )
    appended_results: tuple[DbtNodeExecutionResult, ...] = tuple(
        result for result in results if result.unique_id not in streamed_unique_ids
    )
    streamed_result_count: int = len(results) - len(appended_results)
    for offset, result in enumerate(appended_results, start=1):
        render_dbt_node_result(
            stream=stdout_stream,
            style=style,
            result=result,
            display_index=streamed_result_count + offset,
            display_total=expected_total if expected_total is not None else len(results),
        )
        if on_node_result is not None:
            on_node_result(result)
    if on_progress is not None:
        on_progress("Finalized dbt run.")
    return DbtCommandExecutionResult(returncode=returncode, node_results=results)


def build_merged_dbt_execution_argv(
    *,
    command: DbtInteropCommand,
    options: DbtCliOptions,
    routed_args: tuple[str, ...],
    plan: DbtInteropPlan,
) -> tuple[str, ...] | None:
    """Merge original dbt selection with dbt models required by SQLBuild work."""

    required_terms: tuple[str, ...] = plan.dbt_required_selector_terms
    if command == DbtInteropCommand.TEST:
        test_nodes: tuple[DbtLsNode, ...] = dbt_test_execution_nodes(plan=plan)
        if not test_nodes:
            return None
        merged_args: tuple[str, ...] = _replace_dbt_select_terms(
            args=_strip_resolved_dbt_options(routed_args),
            select_terms=tuple(node.selector_term for node in test_nodes),
        )
    elif not plan.dbt_selected_unique_ids and not required_terms:
        return None
    else:
        merged_args = _merge_dbt_select_terms(
            args=_strip_resolved_dbt_options(routed_args),
            extra_terms=required_terms,
        )
    return build_dbt_command_argv(
        dbt_executable=plan.dbt_command_argv[0],
        command=command.value,
        options=options,
        args=merged_args,
    )


def dbt_test_execution_nodes(*, plan: DbtInteropPlan) -> tuple[DbtLsNode, ...]:
    """Return the deduplicated dbt tests selected during interop planning."""

    selected: list[DbtLsNode] = []
    seen: set[str] = set()
    for node in plan.dbt_selected_nodes:
        if node.resource_type not in (
            DbtSupportedResourceType.TEST,
            DbtSupportedResourceType.UNIT_TEST,
        ):
            continue
        if node.unique_id in seen:
            continue
        seen.add(node.unique_id)
        selected.append(node)
    return tuple(selected)


def build_failed_sqlbuild_model_names(
    *,
    graph: DbtCombinedGraph,
    manifest: DbtManifestIndex,
    node_results: tuple[DbtNodeExecutionResult, ...],
) -> tuple[str, ...]:
    """Return SQLBuild models downstream of actual failed or skipped dbt work."""

    failed_unique_ids: set[str] = set()
    for result in node_results:
        if result.status.lower() in DBT_EXECUTION_SUCCESS_STATUSES:
            continue
        if result.resource_type == DbtSupportedResourceType.MODEL:
            failed_unique_ids.add(result.unique_id)
        elif result.resource_type in (
            DbtSupportedResourceType.TEST,
            DbtSupportedResourceType.UNIT_TEST,
        ):
            failed_unique_ids.update(
                manifest.validation_depends_on_nodes_by_unique_id.get(result.unique_id, ())
            )
    names: set[str] = set()
    for unique_id in failed_unique_ids:
        downstream: frozenset[DbtCombinedGraphKey] = expand_combined_downstream(
            key=dbt_model_graph_key(unique_id),
            downstream=graph.downstream_deps,
        )
        for key in downstream:
            if (
                key.owner == DbtCombinedGraphOwner.SQLBUILD
                and key.resource_type == DbtCombinedGraphResourceType.MODEL
            ):
                names.add(key.name)
    return tuple(sorted(names))


def render_dbt_execution_summary_footer(
    *, node_results: tuple[DbtNodeExecutionResult, ...], use_color: bool
) -> str | None:
    """Render a PASS/WARN/FAIL/SKIP/TOTAL footer for executed dbt nodes."""

    if not node_results:
        return None
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    elapsed: float = 0.0
    for result in node_results:
        status: str = result.status.lower()
        if result.execution_time is not None:
            elapsed += result.execution_time
        if status in DBT_EXECUTION_WARN_STATUSES:
            warn_count += 1
        elif status in DBT_EXECUTION_FAIL_STATUSES:
            fail_count += 1
        elif status in DBT_EXECUTION_SKIP_STATUSES:
            skip_count += 1
        elif status in DBT_EXECUTION_SUCCESS_STATUSES:
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
    status: TransientStatusReporter = TransientStatusReporter(stream=stream, use_color=use_color)
    status.start("Resolving dbt execution selection...")
    start: float = time.monotonic()
    try:
        result: DbtCommandResult = runner.invoke(argv=ls_argv, cwd=options.project_dir)
    finally:
        status.complete(
            message=f"Resolved dbt execution selection. ({time.monotonic() - start:.2f}s)"
        )
    if result.returncode != 0:
        return None
    return len(parse_dbt_ls_json_lines(stdout=result.stdout))


def _dbt_ls_argv_from_execution_argv(argv: tuple[str, ...]) -> tuple[str, ...] | None:
    if len(argv) < _COMMAND_AND_SUBCOMMAND_ARGUMENT_COUNT:
        return None
    converted: list[str] = [argv[0], "ls", "--output", "json"]
    for arg in argv[2:]:
        if arg in _DBT_LS_EXCLUDED_EXECUTION_FLAGS:
            continue
        converted.append(arg)
    return tuple(converted)


def _append_missing_run_results(
    *,
    results: tuple[DbtNodeExecutionResult, ...],
    target_path: Path | None,
    expected_unique_ids: frozenset[str] | None = None,
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
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return results
    raw_results: list[object] = cast(list[object], payload["results"])
    appended: list[DbtNodeExecutionResult] = list(results)
    for index, raw_result in enumerate(raw_results, start=1):
        if not isinstance(raw_result, dict):
            continue
        result_payload: dict[str, object] = cast(dict[str, object], raw_result)
        unique_id: object = result_payload.get("unique_id")
        status: object = result_payload.get("status")
        if not isinstance(unique_id, str) or unique_id in existing_unique_ids:
            continue
        if expected_unique_ids is not None and unique_id not in expected_unique_ids:
            continue
        appended.append(
            DbtNodeExecutionResult(
                unique_id=unique_id,
                resource_type=_resource_type_from_unique_id(unique_id),
                node_name=_node_name_from_unique_id(unique_id),
                status=status if isinstance(status, str) else "unknown",
                index=index,
                total=len(raw_results),
                execution_time=_execution_time_from_run_result(result_payload),
                messages=_messages_from_run_result(result_payload),
            )
        )
    return tuple(appended)


def _effective_dbt_target_path(*, options: DbtCliOptions) -> Path | None:
    if options.target_path is not None:
        return options.target_path
    if options.project_dir is not None:
        return options.project_dir / "target"
    return None


def _resource_type_from_unique_id(unique_id: str) -> str:
    return (
        unique_id.split(DBT_UNIQUE_ID_SEPARATOR, 1)[0]
        if DBT_UNIQUE_ID_SEPARATOR in unique_id
        else "node"
    )


def _node_name_from_unique_id(unique_id: str) -> str:
    return unique_id.rsplit(DBT_UNIQUE_ID_SEPARATOR, 1)[-1]


def _execution_time_from_run_result(raw_result: dict[str, object]) -> float | None:
    value: object = raw_result.get("execution_time")
    return float(value) if isinstance(value, int | float) else None


def _messages_from_run_result(raw_result: dict[str, object]) -> tuple[DbtNodeMessage, ...]:
    message: object = raw_result.get("message")
    if isinstance(message, str) and message.strip():
        return (DbtNodeMessage(level="error", message=message.strip()),)
    failures: object = raw_result.get("failures")
    if isinstance(failures, int) and failures > 0:
        return (DbtNodeMessage(level="error", message=f"{failures} failure(s)"),)
    return ()


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
        if arg == DBT_DEFER_FLAG:
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
    if DBT_SELECT_FLAG not in args:
        return (*args, DBT_SELECT_FLAG, *extra_terms)
    merged: list[str] = []
    index: int = 0
    while index < len(args):
        token: str = args[index]
        merged.append(token)
        index += 1
        if token != DBT_SELECT_FLAG:
            continue
        while index < len(args) and not args[index].startswith("--"):
            merged.append(args[index])
            index += 1
        merged.extend(term for term in extra_terms if term not in merged)
    return tuple(merged)


def _replace_dbt_select_terms(
    *, args: tuple[str, ...], select_terms: tuple[str, ...]
) -> tuple[str, ...]:
    replaced: list[str] = []
    index: int = 0
    while index < len(args):
        token: str = args[index]
        if token != DBT_SELECT_FLAG:
            replaced.append(token)
            index += 1
            continue
        index += 1
        while index < len(args) and not args[index].startswith("--"):
            index += 1
    return (*replaced, DBT_SELECT_FLAG, *select_terms)
