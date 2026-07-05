"""Mutable Python node run state."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


class PythonNodeRunState:
    """Same-run result store for Python DAG nodes."""

    def __init__(
        self,
        results_by_function: dict[object, PythonNodeExecutionResult] | None = None,
    ) -> None:
        self.results_by_function = results_by_function or {}

    def record_result(
        self,
        *,
        node_function: Callable[..., object],
        result: PythonNodeExecutionResult,
    ) -> None:
        self.results_by_function[node_function] = result
        self.results_by_function[("name", result.node_name)] = result
