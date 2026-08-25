"""Mutable direct Python lifecycle state."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TextIO, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.build_python_nodes.python_lifecycle_selection import (
    load_result_key_or_none,
    python_node_result_names,
    sql_loader_functions_for_lifecycle_handoff,
)
from sqlbuild.cli.commands._helpers.build_python_nodes.python_node_output import (
    write_python_node_results,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


class DirectPythonLifecycleState:
    """Mutable state for direct-mode Python lifecycle execution."""

    def __init__(self, **kwargs: object) -> None:
        self.plan_output = cast(PlanOutput, kwargs["plan_output"])
        self.discovered_inputs = cast(DiscoveredProjectInputs, kwargs["discovered_inputs"])
        self.adapter = cast(BaseAdapter, kwargs["adapter"])
        self.progress_stream = cast(TextIO, kwargs["progress_stream"])
        self.use_color = cast(bool, kwargs["use_color"])
        self.base_on_node_complete = cast(Callable[[object], None], kwargs["base_on_node_complete"])
        self.read_side_connection = kwargs["read_side_connection"]
        self.read_side_tracker = cast(Any | None, kwargs["read_side_tracker"])
        self.ingress_python_results = cast(
            tuple[PythonNodeExecutionResult, ...], kwargs["ingress_python_results"]
        )
        self.ingress_load_results = cast(
            tuple[LoadExecutionResult, ...], kwargs["ingress_load_results"]
        )
        self.ingress_loader_names = cast(frozenset[str], kwargs["ingress_loader_names"])

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
