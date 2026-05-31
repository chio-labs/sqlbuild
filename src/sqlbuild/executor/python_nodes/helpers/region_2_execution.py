"""Region 2 SQL-read Python lifecycle execution helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.python_nodes.models import DiscoveredPythonNode, PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.helpers.region_1_execution import _to_executable_python_node
from sqlbuild.executor.python_nodes.main.ready import run_ready_python_node
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult, PythonNodeRunState
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.models import SqlResourceRef


class Region2PythonExecutionTracker:
    """Dispatch selected read-only Python nodes as SQL dependencies complete."""

    def __init__(
        self,
        *,
        python_graph: PythonNodeGraph,
        selected_python_names: frozenset[str],
        adapter: BaseAdapter,
        connection_config: dict[str, object],
        connection: Any,
        run_id: str,
        environment: str | None,
        vars: dict[str, object],
        is_reload: bool,
        default_database: str | None = None,
        default_schema: str | None = None,
        relation_targets: dict[SqlResourceRef, str] | None = None,
        start_cursor_ts: datetime | None = None,
        end_cursor_ts: datetime | None = None,
        start_cursor_int: int | None = None,
        end_cursor_int: int | None = None,
    ) -> None:
        self._python_graph: PythonNodeGraph = python_graph
        self._selected_python_names: frozenset[str] = selected_python_names
        self._adapter: BaseAdapter = adapter
        self._connection_config: dict[str, object] = connection_config
        self._connection: Any = connection
        self._run_id: str = run_id
        self._environment: str | None = environment
        self._vars: dict[str, object] = vars
        self._is_reload: bool = is_reload
        self._default_database: str | None = default_database
        self._default_schema: str | None = default_schema
        self._relation_targets: dict[SqlResourceRef, str] = (
            {} if relation_targets is None else relation_targets
        )
        self._start_cursor_ts: datetime | None = start_cursor_ts
        self._end_cursor_ts: datetime | None = end_cursor_ts
        self._start_cursor_int: int | None = start_cursor_int
        self._end_cursor_int: int | None = end_cursor_int
        self._completed_sql_names: set[str] = set()
        self._failed_sql_names: set[str] = set()
        self._completed_python_names: set[str] = set()
        self._results_by_name: dict[str, PythonNodeExecutionResult] = {}
        self._run_state: PythonNodeRunState = PythonNodeRunState()

    @property
    def results(self) -> tuple[PythonNodeExecutionResult, ...]:
        return tuple(self._results_by_name.values())

    @property
    def completed_python_names(self) -> frozenset[str]:
        return frozenset(self._completed_python_names)

    def finalize_unrun_python_nodes(self) -> tuple[PythonNodeExecutionResult, ...]:
        """Record selected Python nodes that could not run after SQL scheduling finished."""

        finalized_results: list[PythonNodeExecutionResult] = []
        node_name: str
        for node_name in sorted(self._selected_python_names):
            if node_name in self._completed_python_names:
                continue
            node: DiscoveredPythonNode = self._python_graph.nodes_by_name[node_name]
            result: PythonNodeExecutionResult = PythonNodeExecutionResult(
                node_name=node.name,
                kind=node.kind,
                status=PythonNodeStatus.SKIPPED,
                skip_reason=self._unrun_reason(node),
            )
            self._results_by_name[node.name] = result
            self._completed_python_names.add(node.name)
            finalized_results.append(result)
        return tuple(finalized_results)

    def record_sql_result(self, result: object) -> None:
        """Record one SQL/load result and dispatch newly-ready Python nodes."""

        sql_name: str | None = _sql_result_name(result)
        if sql_name is None:
            return
        if _sql_result_failed(result):
            self._failed_sql_names.add(sql_name)
        else:
            self._completed_sql_names.add(sql_name)
        self.dispatch_ready_python_nodes()

    def dispatch_ready_python_nodes(self) -> None:
        """Run all currently-ready selected Python nodes."""

        progressed: bool = True
        while progressed:
            progressed = False
            node_name: str
            for node_name in sorted(self._selected_python_names):
                if node_name in self._completed_python_names:
                    continue
                node: DiscoveredPythonNode = self._python_graph.nodes_by_name[node_name]
                if node.kind not in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
                    continue
                if not self._sql_dependencies_satisfied(node):
                    continue
                if not self._python_dependencies_satisfied(node):
                    continue
                self._execute_python_node(node)
                progressed = True

    def _sql_dependencies_satisfied(self, node: DiscoveredPythonNode) -> bool:
        sql_dep_name: str
        for sql_dep_name in (dependency.name for dependency in node.sql_deps):
            if sql_dep_name in self._failed_sql_names:
                return False
            if sql_dep_name not in self._completed_sql_names:
                return False
        return True

    def _python_dependencies_satisfied(self, node: DiscoveredPythonNode) -> bool:
        upstream_name: str
        for upstream_name in self._python_graph.upstream_deps.get(node.name, ()):
            if upstream_name in self._selected_python_names:
                if upstream_name not in self._completed_python_names:
                    return False
        return True

    def _execute_python_node(self, node: DiscoveredPythonNode) -> None:
        result: PythonNodeExecutionResult = run_ready_python_node(
            node=_to_executable_python_node(node),
            upstream_results=tuple(
                self._results_by_name[upstream_name]
                for upstream_name in self._python_graph.upstream_deps.get(node.name, ())
                if upstream_name in self._results_by_name
            ),
            adapter=self._adapter,
            connection_config=self._connection_config,
            connection=self._connection,
            run_id=self._run_id,
            environment=self._environment,
            vars=self._vars,
            is_reload=self._is_reload,
            statement_recorder=StatementRecorder(),
            run_state=self._run_state,
            default_database=self._default_database,
            default_schema=self._default_schema,
            relation_targets=self._relation_targets,
            start_cursor_ts=self._start_cursor_ts,
            end_cursor_ts=self._end_cursor_ts,
            start_cursor_int=self._start_cursor_int,
            end_cursor_int=self._end_cursor_int,
        )
        self._run_state.record_result(node_function=node.function, result=result)
        self._results_by_name[node.name] = result
        self._completed_python_names.add(node.name)

    def _unrun_reason(self, node: DiscoveredPythonNode) -> str:
        sql_dep_name: str
        for sql_dep_name in (dependency.name for dependency in node.sql_deps):
            if sql_dep_name in self._failed_sql_names:
                return f"Upstream SQL resource did not succeed: {sql_dep_name}"
            if sql_dep_name not in self._completed_sql_names:
                return f"Upstream SQL resource did not complete: {sql_dep_name}"
        upstream_name: str
        for upstream_name in self._python_graph.upstream_deps.get(node.name, ()):
            if upstream_name in self._selected_python_names:
                return f"Upstream Python node did not complete: {upstream_name}"
        return "Region 2 Python node did not become ready"


def _sql_result_name(result: object) -> str | None:
    if isinstance(result, ModelExecutionResult):
        return result.model_name
    if isinstance(result, LoadExecutionResult):
        return result.source_name
    return None


def _sql_result_failed(result: object) -> bool:
    if isinstance(result, ModelExecutionResult | LoadExecutionResult):
        return result.status == ExecutionStatus.FAILED
    return False
