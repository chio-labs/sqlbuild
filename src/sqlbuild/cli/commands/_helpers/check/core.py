"""Helpers for the sqb check command."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild._native import (
    build_python_relation_targets,
    resolve_python_check_excludes,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
)
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
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry


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
    *,
    adapter: BaseAdapter,
    pipeline_result: CompilePipelineResult,
    python_graph: PythonNodeGraph,
    selected_python_names: frozenset[str],
) -> dict[SqlResourceRef, str]:
    """Return SQL relation locations available to Python check dependencies."""

    return build_python_relation_targets(
        adapter=adapter,
        project=pipeline_result.project,
        plan_output=pipeline_result.plan_output,
        required_refs=python_graph.selected_sql_refs(
            selected_names=selected_python_names,
        ),
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
    validation_refs: frozenset[SqlResourceRef] | None = None,
    project_relations: dict[SqlResourceRef, str] | None = None,
    providers: ProviderContainer | None = None,
) -> tuple[PythonNodeExecutionResult, ...]:
    """Run read-side Python dependencies for checks against existing SQL relations."""

    read_side_names: frozenset[str] = lifecycle_plan.read_side_python_node_names
    read_side_refs: frozenset[SqlResourceRef] = _read_side_sql_refs(
        read_side_names=read_side_names, python_graph=python_graph
    )
    refs_to_validate: frozenset[SqlResourceRef] = (
        validation_refs if validation_refs is not None else read_side_refs
    )
    sql_refs: tuple[SqlResourceRef, ...] = tuple(
        sorted(
            refs_to_validate,
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
    if not read_side_names:
        return ()
    tracker: Any = create_read_side_python_execution_tracker(
        python_graph=python_graph,
        selected_python_names=read_side_names,
        scheduled_sql_names=frozenset(),
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
            project_relations=project_relations,
            providers=providers,
        ),
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


def check_results_failed(results: tuple[PythonCheckExecutionResult, ...]) -> bool:
    """Return whether any Python check produced an error-severity failure."""

    return any(result.failed for result in results)


def relevant_check_functions(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    python_graph: PythonNodeGraph,
    exclude: tuple[str, ...],
    selected_dependency_names: frozenset[str],
    completed_sql_names: frozenset[str] = frozenset(),
) -> tuple[DiscoveredCheckFunction, ...]:
    """Return non-excluded checks whose Python and SQL dependencies all ran in this build."""

    excluded_names: frozenset[str] = resolve_python_check_excludes(
        graph=python_graph, exclude=exclude
    )
    check_names: set[str] = set()
    for node in python_graph.nodes:
        if node.kind != PythonNodeKind.CHECK:
            continue
        if node.name in excluded_names:
            continue
        upstream_names: tuple[str, ...] = python_graph.upstream_deps.get(node.name, ())
        sql_names: tuple[str, ...] = tuple(sql_ref.name for sql_ref in node.sql_deps)
        if (
            (upstream_names or sql_names)
            and all(name in selected_dependency_names for name in upstream_names)
            and all(name in completed_sql_names for name in sql_names)
        ):
            check_names.add(node.name)
    return tuple(check for check in discovered_inputs.check_functions if check.name in check_names)


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
    elif ref.kind == SqlResourceRefKind.SEED:
        seed_target: CompiledRelationLocation | None = (
            pipeline_result.plan_output.seed_locations.get(ref.name)
        )
        if seed_target is None:
            raise CliUserError(
                f"Python check dependency requires unknown seed '{ref.name}'",
                code="C682",
            )
        exists = relation_lookup.exists(
            database=seed_target.database, schema=seed_target.schema, name=seed_target.name
        )
        relation = resolve_relation_location_qualified_name(adapter=adapter, location=seed_target)
    elif ref.kind == SqlResourceRefKind.SOURCE:
        source: SourceEntry | None = (pipeline_result.plan_output.python_source_entries).get(
            ref.name
        )
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
    if ref.kind == SqlResourceRefKind.SEED:
        seed_target: CompiledRelationLocation | None = (
            pipeline_result.plan_output.seed_locations.get(ref.name)
        )
        if seed_target is None:
            return None
        return (seed_target.database, seed_target.schema, seed_target.name)
    if ref.kind == SqlResourceRefKind.SOURCE:
        source: SourceEntry | None = (pipeline_result.plan_output.python_source_entries).get(
            ref.name
        )
        if source is None or source.expression is not None or source.table is None:
            return None
        return (source.database, source.schema, source.table)
    return None


def _sql_ref_sort_key(ref: SqlResourceRef) -> tuple[str, str]:
    return (ref.kind.value, ref.name)
