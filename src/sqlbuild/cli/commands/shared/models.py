"""Shared CLI command models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.cli.commands.shared.helpers.python_nodes.core import (
    load_result_key_or_none,
    python_node_result_names,
    sql_loader_functions_for_lifecycle_handoff,
    write_python_node_results,
)
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


@dataclass(frozen=True)
class AdapterConnectionContext:
    """Resolved adapter and connection configuration for one CLI command."""

    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]


@dataclass(frozen=True)
class CommandProgressReporters:
    """Connection and planning progress reporters bound to one output stream."""

    connection: ConnectionProgressReporter
    planning: PlanningProgressReporter


@dataclass(frozen=True)
class NestedProgressChildRow:
    """One child row rendered below a completed nested progress item."""

    label: str
    name: str
    status_text: str
    detail: str = ""


@dataclass
class StandardPythonLifecycleState:
    """Mutable state for standard-mode Python lifecycle execution."""

    plan_output: PlanOutput
    discovered_inputs: DiscoveredProjectInputs
    adapter: BaseAdapter
    progress_stream: TextIO
    use_color: bool
    base_on_node_complete: Callable[[object], None]
    read_side_connection: object | None
    read_side_tracker: Any | None
    ingress_python_results: tuple[PythonNodeExecutionResult, ...]
    ingress_load_results: tuple[LoadExecutionResult, ...]
    ingress_loader_names: frozenset[str]

    @property
    def ingress_failed(self) -> bool:
        return any(
            result.status == PythonNodeStatus.FAILED for result in self.ingress_python_results
        ) or any(result.status == ExecutionStatus.FAILED for result in self.ingress_load_results)

    @property
    def python_results(self) -> tuple[PythonNodeExecutionResult, ...]:
        read_side_results: tuple[PythonNodeExecutionResult, ...] = (
            () if self.read_side_tracker is None else self.read_side_tracker.results
        )
        return (*self.ingress_python_results, *read_side_results)

    @property
    def loader_functions(self) -> tuple[DiscoveredLoaderFunction, ...]:
        return sql_loader_functions_for_lifecycle_handoff(
            discovered_inputs=self.discovered_inputs,
            ingress_loader_names=self.ingress_loader_names,
        )

    @property
    def precompleted_keys(self) -> frozenset[CompiledObjectKey]:
        return frozenset(
            key
            for load_result in self.ingress_load_results
            if (key := load_result_key_or_none(plan=self.plan_output, result=load_result))
            is not None
        )

    @property
    def blocked_keys(self) -> frozenset[CompiledObjectKey]:
        return frozenset(
            key
            for load_result in self.ingress_load_results
            if load_result.status != ExecutionStatus.SUCCESS
            if (key := load_result_key_or_none(plan=self.plan_output, result=load_result))
            is not None
        )

    def on_node_complete(self, node_result: object) -> None:
        self.base_on_node_complete(node_result)
        if self.read_side_tracker is None:
            return
        previous_names: frozenset[str] = python_node_result_names(self.read_side_tracker.results)
        self.read_side_tracker.record_sql_result(node_result)
        new_results: tuple[PythonNodeExecutionResult, ...] = tuple(
            result
            for result in self.read_side_tracker.results
            if result.node_name not in previous_names
        )
        if new_results:
            write_python_node_results(
                stream=self.progress_stream,
                results=new_results,
                use_color=self.use_color,
            )

    def finalize(self) -> None:
        if self.read_side_connection is not None:
            self.adapter.close(self.read_side_connection)
            self.read_side_connection = None
        if self.read_side_tracker is None:
            return
        finalized_results: tuple[PythonNodeExecutionResult, ...] = (
            self.read_side_tracker.finalize_unrun_python_nodes()
        )
        if finalized_results:
            write_python_node_results(
                stream=self.progress_stream,
                results=finalized_results,
                use_color=self.use_color,
            )
