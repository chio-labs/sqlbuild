"""Python-node selection and SQL loader lifecycle handoff."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


def task_asset_python_node_names(
    *, selected_names: frozenset[str], discovered_inputs: DiscoveredProjectInputs
) -> frozenset[str]:
    """Return selected task/asset names, excluding loaders and checks."""

    task_asset_names: set[str] = {
        *(node.name for node in discovered_inputs.task_functions),
        *(node.name for node in discovered_inputs.asset_functions),
    }
    return frozenset(name for name in selected_names if name in task_asset_names)


def sql_loader_functions_for_lifecycle_handoff(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    ingress_loader_names: frozenset[str],
) -> tuple[DiscoveredLoaderFunction, ...]:
    """Return SQL-stage loaders after Python ingress handled mixed dependencies."""

    loader_functions: frozenset[object] = frozenset(
        loader.function for loader in discovered_inputs.loader_functions
    )
    handoff_loaders: list[DiscoveredLoaderFunction] = []
    for loader in discovered_inputs.loader_functions:
        dependencies: list[object] = []
        for dependency in loader.depends_on:
            if dependency in loader_functions or loader.name not in ingress_loader_names:
                dependencies.append(dependency)
        handoff_loaders.append(replace(loader, depends_on=tuple(dependencies)))
    return tuple(handoff_loaders)


def python_node_result_names(results: tuple[PythonNodeExecutionResult, ...]) -> frozenset[str]:
    """Return Python-node result names."""

    return frozenset(result.node_name for result in results)


def load_result_key_or_none(
    *, plan: PlanOutput, result: LoadExecutionResult
) -> CompiledObjectKey | None:
    """Return the plan key for a source-load result when it is part of the SQL plan."""

    for entry in plan.source_load_entries:
        if entry.name == result.source_name:
            return entry.key
    return None
