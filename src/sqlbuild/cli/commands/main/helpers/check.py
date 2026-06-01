"""Helpers for the sqb check command."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TextIO

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.python_nodes.main.selectors import resolve_python_nodes_from_selectors
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
)
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.spec.models.source import SourceEntry


def resolve_selected_check_names(
    *, graph: PythonNodeGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> frozenset[str]:
    """Resolve sqb check selectors into check/dependency Python node names."""

    if select:
        return resolve_python_nodes_from_selectors(select=select, exclude=exclude, graph=graph)
    check_names: frozenset[str] = frozenset(
        node.name for node in graph.nodes if node.kind == PythonNodeKind.CHECK
    )
    selected: set[str] = set(check_names)
    check_name: str
    for check_name in check_names:
        selected.update(_upstream_closure(name=check_name, graph=graph))
    excluded: frozenset[str] = (
        resolve_python_nodes_from_selectors(select=exclude, exclude=(), graph=graph)
        if exclude
        else frozenset()
    )
    return frozenset(selected - excluded)


def validate_selected_check_dependencies(
    *, graph: PythonNodeGraph, selected_names: frozenset[str], check_names: frozenset[str]
) -> None:
    """Validate selected checks have explicitly selected Python dependencies."""

    check_name: str
    for check_name in check_names:
        upstream_name: str
        for upstream_name in graph.upstream_deps.get(check_name, ()):
            if upstream_name in selected_names:
                continue
            raise CliUserError(
                f"Python check '{check_name}' depends on unselected Python node "
                f"'{upstream_name}'; select it directly or use upstream expansion",
                code="C681",
            )


def record_python_run_state_results(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    run_state: PythonNodeRunState,
    python_results: tuple[PythonNodeExecutionResult, ...],
    load_results: tuple[LoadExecutionResult, ...] = (),
    source_map: dict[str, SourceEntry] | None = None,
) -> None:
    """Record Python and loader results in the Python run-state."""

    result_by_name: dict[str, PythonNodeExecutionResult] = {
        result.node_name: result for result in python_results
    }
    node_by_name: dict[str, Callable[..., object]] = {
        **{task.name: task.function for task in discovered_inputs.task_functions},
        **{asset.name: asset.function for asset in discovered_inputs.asset_functions},
    }
    for node_name, node_function in node_by_name.items():
        result: PythonNodeExecutionResult | None = result_by_name.get(node_name)
        if result is not None:
            run_state.record_result(node_function=node_function, result=result)
    if source_map is not None:
        result_by_loader_name: dict[str, LoadExecutionResult] = load_results_by_loader_name(
            source_map=source_map,
            load_results=load_results,
        )
    else:
        result_by_loader_name = {}
    for loader in discovered_inputs.loader_functions:
        load_result: LoadExecutionResult | None = result_by_loader_name.get(loader.name)
        if load_result is None:
            continue
        run_state.record_result(
            node_function=loader.function,
            result=_load_result_to_python_result(node_name=loader.name, result=load_result),
        )


def load_results_by_loader_name(
    *, source_map: dict[str, SourceEntry], load_results: tuple[LoadExecutionResult, ...]
) -> dict[str, LoadExecutionResult]:
    """Return load results keyed by loader name for check dependency lookup."""

    loader_by_source_name: dict[str, str] = {
        name: source.loader for name, source in source_map.items() if source.loader is not None
    }
    return {
        loader_name: result
        for result in load_results
        if (loader_name := loader_by_source_name.get(result.source_name)) is not None
    }


def write_check_results(
    *,
    stream: TextIO,
    results: tuple[PythonCheckExecutionResult, ...],
    use_color: bool,
    check_functions: tuple[DiscoveredCheckFunction, ...] = (),
    python_graph: PythonNodeGraph | None = None,
) -> None:
    """Write human-readable check result rows."""

    style: CliStyle = CliStyle(use_color=use_color)
    result_by_name: dict[str, PythonCheckExecutionResult] = {
        result.node_name: result for result in results
    }
    grouped_names: dict[str, list[str]] = _group_check_names(
        results=results,
        check_functions=check_functions,
        python_graph=python_graph,
    )
    stream.write("\n")
    group_label: str
    result_names: list[str]
    for group_label, result_names in grouped_names.items():
        stream.write(f"Python checks: {group_label}\n\n")
        for result_name in result_names:
            result: PythonCheckExecutionResult = result_by_name[result_name]
            _write_check_result_row(stream=stream, result=result, style=style)
        stream.write("\n")


def format_check_json(*, results: tuple[PythonCheckExecutionResult, ...]) -> str:
    """Format check execution JSON."""

    payload: dict[str, object] = {
        "version": 1,
        "command": "check",
        "status": "failed" if check_results_failed(results) else "success",
        "summary": {
            "pass_count": sum(1 for result in results if result.passed),
            "warn_count": sum(1 for result in results if result.warned),
            "fail_count": sum(1 for result in results if result.failed),
            "total_count": len(results),
        },
        "checks": [
            {
                "kind": "python_check",
                "name": result.node_name,
                "display_name": result.node_name,
                "check_id": f"python_check:{result.node_name}",
                "status": "pass" if result.passed else "warn" if result.warned else "fail",
                "passed": result.passed,
                "severity": result.severity.value,
                "message": result.message,
                "error_message": result.error_message,
                "metadata": result.metadata,
            }
            for result in results
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def check_results_failed(results: tuple[PythonCheckExecutionResult, ...]) -> bool:
    """Return whether any Python check produced an error-severity failure."""

    return any(result.failed for result in results)


def relevant_check_functions(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    python_graph: PythonNodeGraph,
    exclude: tuple[str, ...],
    selected_dependency_names: frozenset[str],
) -> tuple[DiscoveredCheckFunction, ...]:
    """Return checks whose Python dependencies all ran and were not excluded."""

    excluded_names: frozenset[str] = _resolve_python_check_excludes(
        exclude=exclude, python_graph=python_graph
    )
    check_names: set[str] = set()
    for node in python_graph.nodes:
        if node.kind != PythonNodeKind.CHECK:
            continue
        if node.name in excluded_names:
            continue
        upstream_names: tuple[str, ...] = python_graph.upstream_deps.get(node.name, ())
        if upstream_names and all(name in selected_dependency_names for name in upstream_names):
            check_names.add(node.name)
    return tuple(check for check in discovered_inputs.check_functions if check.name in check_names)


def _resolve_python_check_excludes(
    *, exclude: tuple[str, ...], python_graph: PythonNodeGraph
) -> frozenset[str]:
    excluded: set[str] = set()
    raw_exclude: str
    for raw_exclude in exclude:
        token: str
        for token in raw_exclude.split():
            try:
                excluded.update(
                    resolve_python_nodes_from_selectors(
                        select=(token,), exclude=(), graph=python_graph
                    )
                )
            except PlannerInputError as error:
                if error.code in {"S007", "S008", "S009"}:
                    continue
                raise
    return frozenset(excluded)


def _upstream_closure(*, name: str, graph: PythonNodeGraph) -> frozenset[str]:
    visited: set[str] = set()
    pending: list[str] = list(graph.upstream_deps.get(name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in visited:
            continue
        visited.add(current)
        pending.extend(graph.upstream_deps.get(current, ()))
    return frozenset(visited)


def _load_result_to_python_result(
    *, node_name: str, result: LoadExecutionResult
) -> PythonNodeExecutionResult:
    status: PythonNodeStatus = (
        PythonNodeStatus.SUCCESS
        if result.status == ExecutionStatus.SUCCESS
        else PythonNodeStatus.SKIPPED
        if result.status == ExecutionStatus.SKIPPED
        else PythonNodeStatus.FAILED
    )
    return PythonNodeExecutionResult(
        node_name=node_name,
        kind=PythonNodeKind.LOADER,
        status=status,
        payload=result,
        error_message=result.error_message,
    )


def _group_check_names(
    *,
    results: tuple[PythonCheckExecutionResult, ...],
    check_functions: tuple[DiscoveredCheckFunction, ...],
    python_graph: PythonNodeGraph | None,
) -> dict[str, list[str]]:
    check_by_name: dict[str, DiscoveredCheckFunction] = {
        check.name: check for check in check_functions
    }
    groups: dict[str, list[str]] = {}
    result: PythonCheckExecutionResult
    for result in results:
        group_label: str = _check_group_label(
            check=check_by_name.get(result.node_name),
            result_name=result.node_name,
            python_graph=python_graph,
        )
        groups.setdefault(group_label, []).append(result.node_name)
    return groups


def _check_group_label(
    *,
    check: DiscoveredCheckFunction | None,
    result_name: str,
    python_graph: PythonNodeGraph | None,
) -> str:
    if python_graph is not None:
        upstream_names: tuple[str, ...] = python_graph.upstream_deps.get(result_name, ())
        if len(upstream_names) == 1:
            return upstream_names[0]
        if len(upstream_names) > 1:
            return (
                check.group if check is not None and check.group is not None else "multi-dependency"
            )
    if check is not None and check.group is not None:
        return check.group
    return "ungrouped"


def _write_check_result_row(
    *, stream: TextIO, result: PythonCheckExecutionResult, style: CliStyle
) -> None:
    status: str = "PASS" if result.passed else "WARN" if result.warned else "FAIL"
    stream.write(f"  {'check':<10}{result.node_name:<50} {style.status(status)}")
    detail: str | None = result.error_message or result.message
    if detail:
        stream.write(f"  {detail}")
    stream.write("\n")
