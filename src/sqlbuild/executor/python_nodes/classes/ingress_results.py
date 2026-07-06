"""Mutable accumulator for ingress python node and loader results."""

from __future__ import annotations

from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


class IngressResultAccumulator:
    """Per-run store of ingress python node and loader execution results."""

    def __init__(self) -> None:
        self.python_results_by_name: dict[str, PythonNodeExecutionResult] = {}
        self.load_results_by_name: dict[str, LoadExecutionResult] = {}

    def record_python_result(self, *, name: str, result: PythonNodeExecutionResult) -> None:
        """Store the execution result for one python node."""

        self.python_results_by_name[name] = result

    def record_load_result(self, *, name: str, result: LoadExecutionResult) -> None:
        """Store the execution result for one ingress loader."""

        self.load_results_by_name[name] = result
