"""CLI helpers for Python-node output and SQL loader execution handoff."""

from __future__ import annotations

from dataclasses import replace
from typing import TextIO

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.shared.helpers.cli_style import CliStyle


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
    return tuple(
        replace(
            loader,
            depends_on=tuple(
                dependency
                for dependency in loader.depends_on
                if dependency in loader_functions or loader.name not in ingress_loader_names
            ),
        )
        for loader in discovered_inputs.loader_functions
    )


def write_python_node_results(
    *, stream: TextIO, results: tuple[PythonNodeExecutionResult, ...], use_color: bool
) -> None:
    """Write human-readable task/asset execution rows."""

    style: CliStyle = CliStyle(use_color=use_color)
    result: PythonNodeExecutionResult
    for result in results:
        status_text: str = python_node_status_text(result.status)
        stream.write(
            f"  {'python':<10}{result.kind.value:<10}{result.node_name:<50} "
            f"{style.status(status_text)}"
        )
        if result.error_message:
            stream.write(f"  {result.error_message}")
        elif result.skip_reason:
            stream.write(f"  {result.skip_reason}")
        stream.write("\n")
    stream.flush()


def python_node_status_text(status: PythonNodeStatus) -> str:
    """Return the short human status label for a Python-node status."""

    if status == PythonNodeStatus.SUCCESS:
        return "OK"
    if status == PythonNodeStatus.SKIPPED:
        return "SKIP"
    return "FAIL"


def python_node_results_failed(results: tuple[PythonNodeExecutionResult, ...]) -> bool:
    """Return whether any Python-node result failed."""

    return any(result.status == PythonNodeStatus.FAILED for result in results)


def python_node_result_names(results: tuple[PythonNodeExecutionResult, ...]) -> frozenset[str]:
    """Return Python-node result names."""

    return frozenset(result.node_name for result in results)


def load_result_key(*, plan: PlanOutput, result: LoadExecutionResult) -> CompiledObjectKey:
    """Return the plan key for a source-load execution result."""

    key: CompiledObjectKey | None = load_result_key_or_none(plan=plan, result=result)
    if key is not None:
        return key
    raise CliUserError(f"No source-load plan entry found for load result '{result.source_name}'")


def load_result_key_or_none(
    *, plan: PlanOutput, result: LoadExecutionResult
) -> CompiledObjectKey | None:
    """Return the plan key for a source-load result when it is part of the SQL plan."""

    for entry in plan.source_load_entries:
        if entry.name == result.source_name:
            return entry.key
    return None
