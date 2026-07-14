"""Helpers for the sqb check command."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.models import RelationLookup
from sqlbuild.adapter.relation_naming.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.relation_targets import (
    build_python_relation_targets,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.planning.selector_parse import parse_project_selector
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.python_nodes.main.selectors import resolve_python_nodes_from_selectors
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunLifecyclePlan
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.main.read_side import create_read_side_python_execution_tracker
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
    PythonNodeRuntime,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from sqlbuild.spec.contracts.models import SourceEntry

_IGNORED_EXCLUDE_SELECTOR_ERROR_CODES: frozenset[str] = frozenset({"S007", "S008", "S009"})


def resolve_selected_check_names(
    *, graph: PythonNodeGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> frozenset[str]:
    """Resolve sqb check selectors into check names only."""

    _validate_check_selectors(select=(*select, *exclude))
    if select:
        selected_names: frozenset[str] = resolve_python_nodes_from_selectors(
            select=select, exclude=exclude, graph=graph
        )
        return _check_names_from_selection(graph=graph, selected_names=selected_names)
    check_names: frozenset[str] = frozenset(
        node.name for node in graph.nodes if node.kind == PythonNodeKind.CHECK
    )
    excluded: frozenset[str] = (
        resolve_python_nodes_from_selectors(select=exclude, exclude=(), graph=graph)
        if exclude
        else frozenset()
    )
    return frozenset(check_names - excluded)


def _validate_check_selectors(*, select: tuple[str, ...]) -> None:
    raw_selector: str
    for raw_selector in select:
        token: str
        for token in raw_selector.split():
            part: str
            for part in token.split(","):
                parsed: ParsedSelector | PathSelector = parse_project_selector(part)
                if isinstance(parsed, PathSelector) or parsed.upstream or parsed.downstream:
                    raise CliUserError(
                        "sqb check selectors do not support graph operators; "
                        "select checks directly without '+', '~', or path-between expansion",
                        code="C681",
                    )


def _check_names_from_selection(
    *, graph: PythonNodeGraph, selected_names: frozenset[str]
) -> frozenset[str]:
    non_check_names: tuple[str, ...] = tuple(
        sorted(
            name
            for name in selected_names
            if graph.nodes_by_name[name].kind != PythonNodeKind.CHECK
        )
    )
    if non_check_names:
        raise CliUserError(
            "sqb check selectors must resolve only to Python checks; non-check selections: "
            + ", ".join(non_check_names),
            code="C682",
        )
    return selected_names


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


def build_check_relation_targets(
    *, adapter: BaseAdapter, pipeline_result: CompilePipelineResult
) -> dict[SqlResourceRef, str]:
    """Return SQL relation locations available to Python check dependencies."""

    return build_python_relation_targets(
        adapter=adapter,
        project=pipeline_result.project,
        plan_output=pipeline_result.plan_output,
    )


def run_check_read_side_dependencies(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    pipeline_result: CompilePipelineResult,
    python_graph: PythonNodeGraph,
    lifecycle_plan: PythonSqlRunLifecyclePlan,
    relation_targets: dict[SqlResourceRef, str],
    providers: ProviderContainer | None = None,
) -> tuple[PythonNodeExecutionResult, ...]:
    """Run read-side Python dependencies for checks against existing SQL relations."""

    read_side_names: frozenset[str] = lifecycle_plan.read_side_python_node_names
    if not read_side_names:
        return ()
    tracker: Any = create_read_side_python_execution_tracker(
        python_graph=python_graph,
        selected_python_names=read_side_names,
        runtime=PythonNodeRuntime(
            adapter=adapter,
            connection_config=connection_config,
            connection=connection,
            run_id=pipeline_result.project.run_id,
            target=pipeline_result.project.effective_target_name,
            vars=pipeline_result.project.effective_vars,
            is_reload=False,
            default_database=adapter.default_database(),
            default_schema=adapter.default_schema(),
            relation_targets=relation_targets,
            providers=providers,
        ),
    )
    sql_refs: tuple[SqlResourceRef, ...] = tuple(
        sorted(
            _read_side_sql_refs(read_side_names=read_side_names, python_graph=python_graph),
            key=_sql_ref_sort_key,
        )
    )
    relation_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            location
            for sql_ref in sql_refs
            if (location := _check_sql_ref_location(pipeline_result=pipeline_result, ref=sql_ref))
            is not None
        ),
    )
    sql_ref: SqlResourceRef
    for sql_ref in sql_refs:
        _validate_check_sql_ref_exists(
            adapter=adapter,
            pipeline_result=pipeline_result,
            relation_targets=relation_targets,
            relation_lookup=relation_lookup,
            ref=sql_ref,
        )
        if sql_ref.kind == SqlResourceRefKind.MODEL:
            tracker.record_sql_result(
                ModelExecutionResult(model_name=sql_ref.name, status=ExecutionStatus.SUCCESS)
            )
        elif sql_ref.kind == SqlResourceRefKind.SOURCE:
            tracker.record_sql_result(
                LoadExecutionResult(
                    source_name=sql_ref.name,
                    loader_name=sql_ref.name,
                    status=ExecutionStatus.SUCCESS,
                    target=relation_targets[sql_ref],
                    resource_kind=ExecutionResourceKind.SOURCE,
                )
            )
    tracker.dispatch_ready_python_nodes()
    tracker.finalize_unrun_python_nodes()
    return tracker.results


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
                if error.code in _IGNORED_EXCLUDE_SELECTOR_ERROR_CODES:
                    continue
                raise
    return frozenset(excluded)


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


def _read_side_sql_refs(
    *, read_side_names: frozenset[str], python_graph: PythonNodeGraph
) -> frozenset[SqlResourceRef]:
    refs: set[SqlResourceRef] = set()
    node_name: str
    for node_name in read_side_names:
        refs.update(python_graph.nodes_by_name[node_name].sql_deps)
    return frozenset(refs)


def _validate_check_sql_ref_exists(
    *,
    adapter: BaseAdapter,
    pipeline_result: CompilePipelineResult,
    relation_targets: dict[SqlResourceRef, str],
    relation_lookup: RelationLookup,
    ref: SqlResourceRef,
) -> None:
    if ref.kind == SqlResourceRefKind.MODEL:
        target: CompiledRelationLocation | None = pipeline_result.plan_output.model_locations.get(
            ref.name
        )
        if target is None:
            raise CliUserError(
                f"Python check dependency requires unknown SQL model '{ref.name}'",
                code="C682",
            )
        exists: bool = relation_lookup.exists(
            database=target.database, schema=target.schema, name=target.name
        )
        relation: str = resolve_relation_location_qualified_name(adapter=adapter, location=target)
    elif ref.kind == SqlResourceRefKind.SOURCE:
        source: SourceEntry | None = (
            pipeline_result.plan_output.source_read_map or pipeline_result.plan_output.source_map
        ).get(ref.name)
        if source is None or source.expression is not None or source.table is None:
            return
        exists = relation_lookup.exists(
            database=source.database, schema=source.schema, name=source.table
        )
        relation = relation_targets[ref]
    else:
        return
    if exists:
        return
    raise CliUserError(
        "Python check dependency requires existing SQL relation "
        f"'{relation}' for {ref.kind.value} '{ref.name}'; run sqb build first",
        code="C682",
    )


def _check_sql_ref_location(
    *, pipeline_result: CompilePipelineResult, ref: SqlResourceRef
) -> tuple[str | None, str | None, str] | None:
    if ref.kind == SqlResourceRefKind.MODEL:
        target: CompiledRelationLocation | None = pipeline_result.plan_output.model_locations.get(
            ref.name
        )
        if target is None:
            return None
        return (target.database, target.schema, target.name)
    if ref.kind == SqlResourceRefKind.SOURCE:
        source: SourceEntry | None = (
            pipeline_result.plan_output.source_read_map or pipeline_result.plan_output.source_map
        ).get(ref.name)
        if source is None or source.expression is not None or source.table is None:
            return None
        return (source.database, source.schema, source.table)
    return None


def _sql_ref_sort_key(ref: SqlResourceRef) -> tuple[str, str]:
    return (ref.kind.value, ref.name)


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
    stream.write(f"  {'check':<10}{result.node_name:<50} {style.status(status=status)}")
    detail: str | None = result.error_message or result.message
    if detail:
        stream.write(f"  {detail}")
    stream.write("\n")
