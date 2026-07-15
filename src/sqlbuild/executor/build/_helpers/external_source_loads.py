"""Pre-connection execution for external source-load nodes."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.planner.models import PlanOutput, SourceLoadPlanEntry
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.build._helpers.source_node import execute_build_source_node
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildRuntimeParams,
    ExternalSourceLoadResults,
)
from sqlbuild.executor.load.main.build_execution_indexes import build_load_execution_indexes
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.spec.contracts.models import SourceEntry


def run_external_source_loads_before_connections(
    *,
    plan: PlanOutput,
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    runtime: BuildRuntimeParams,
    callbacks: BuildCallbacks,
    precompleted_keys: frozenset[CompiledObjectKey] = frozenset(),
) -> ExternalSourceLoadResults:
    """Run external source-load nodes before SQLBuild opens warehouse connections."""

    loader_functions_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in loader_functions
    }
    external_entries_by_key: dict[CompiledObjectKey, SourceLoadPlanEntry] = {
        entry.key: entry
        for entry in plan.source_load_entries
        if loader_functions_by_name[entry.loader].connection_mode == LoaderConnectionMode.EXTERNAL
        and entry.key not in precompleted_keys
    }
    if not external_entries_by_key:
        return ExternalSourceLoadResults(
            results=(), completed_keys=frozenset(), failed_keys=frozenset()
        )
    _validate_external_entries_are_preconnect_runnable(
        plan=plan,
        external_entries_by_key=external_entries_by_key,
        loader_functions_by_name=loader_functions_by_name,
    )
    loader_ref_entries: dict[Callable[..., object], SourceEntry] = build_load_execution_indexes(
        sources=tuple(plan.source_map.values()),
        loader_functions=loader_functions,
    ).loader_ref_entries
    results: list[LoadExecutionResult] = []
    completed_keys: set[CompiledObjectKey] = set()
    failed_keys: set[CompiledObjectKey] = set()
    key: CompiledObjectKey
    for key in plan.execution_order:
        source_load_entry: SourceLoadPlanEntry | None = external_entries_by_key.get(key)
        if source_load_entry is None:
            continue
        if any(upstream in failed_keys for upstream in plan.upstream_deps.get(key, ())):
            failed_keys.add(key)
            completed_keys.add(key)
            continue
        result: LoadExecutionResult = execute_build_source_node(
            key=key,
            plan=plan,
            loader_functions_by_name=loader_functions_by_name,
            loader_ref_entries=loader_ref_entries,
            adapter=adapter,
            connection_config=connection_config,
            connection=None,
            runtime=runtime,
            callbacks=callbacks,
        )
        results.append(result)
        completed_keys.add(key)
        if result.status != ExecutionStatus.SUCCESS:
            failed_keys.add(key)
        if callbacks.on_node_complete is not None:
            callbacks.on_node_complete(result)
    return ExternalSourceLoadResults(
        results=tuple(results),
        completed_keys=frozenset(completed_keys),
        failed_keys=frozenset(failed_keys),
    )


def _validate_external_entries_are_preconnect_runnable(
    *,
    plan: PlanOutput,
    external_entries_by_key: dict[CompiledObjectKey, SourceLoadPlanEntry],
    loader_functions_by_name: dict[str, DiscoveredLoaderFunction],
) -> None:
    source_entries_by_key: dict[CompiledObjectKey, SourceLoadPlanEntry] = {
        entry.key: entry for entry in plan.source_load_entries
    }
    key: CompiledObjectKey
    for key in external_entries_by_key:
        upstream: CompiledObjectKey
        for upstream in plan.upstream_deps.get(key, ()):
            if upstream not in plan.execution_order:
                continue
            upstream_source_entry: SourceLoadPlanEntry | None = source_entries_by_key.get(upstream)
            if upstream_source_entry is not None:
                upstream_loader: DiscoveredLoaderFunction = loader_functions_by_name[
                    upstream_source_entry.loader
                ]
                if upstream_loader.connection_mode == LoaderConnectionMode.EXTERNAL:
                    continue
                raise ExecutorInputError(
                    f"External loader '{external_entries_by_key[key].loader}' cannot depend on "
                    f"SQLBuild-connection loader '{upstream_loader.name}'. External loaders must "
                    "be runnable before SQLBuild opens warehouse connections."
                )
            raise ExecutorInputError(
                f"External loader '{external_entries_by_key[key].loader}' cannot depend on "
                f"in-plan node '{upstream.name}'. External loaders must be runnable before "
                "SQLBuild opens warehouse connections."
            )
