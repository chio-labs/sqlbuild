"""Internal Python-node execution result models."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.python_nodes.types import (
    PythonNodeFanInAction,
    PythonNodeKind,
    PythonNodeStatus,
    SkipMode,
)
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.constants import MISSING_DEFAULT
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.shared.types import PythonCheckSeverity


@dataclass(frozen=True)
class PythonNodeResult:
    """User-facing successful result returned by a Python node."""

    payload: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    materialized: bool | None = None


@dataclass(frozen=True)
class PythonNodeSkipResult:
    """User-facing skip signal returned by a Python node."""

    reason: str
    mode: SkipMode = SkipMode.SOFT
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PythonCheckResult:
    """User-facing result returned by a Python check node."""

    passed: bool
    message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    severity: PythonCheckSeverity | None = None


@dataclass(frozen=True)
class PythonCheckExecutionResult:
    """Normalized execution outcome for one Python check node."""

    node_name: str
    passed: bool
    severity: PythonCheckSeverity
    message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    error_message: str | None = None

    @property
    def warned(self) -> bool:
        """Return whether this result is a non-failing warning."""

        return not self.passed and self.severity == PythonCheckSeverity.WARN

    @property
    def failed(self) -> bool:
        """Return whether this result is a failing error."""

        return not self.passed and self.severity == PythonCheckSeverity.ERROR


@dataclass(frozen=True)
class PythonNodeExecutionResult:
    """Normalized execution outcome for one Python node."""

    node_name: str
    kind: PythonNodeKind
    status: PythonNodeStatus
    payload: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    materialized: bool | None = None
    skip_mode: SkipMode | None = None
    skip_reason: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class PythonNodeFanInDecision:
    """Scheduler decision for a node after all upstream outcomes are known."""

    action: PythonNodeFanInAction
    reason: str | None = None
    skip_mode: SkipMode | None = None


@dataclass
class PythonNodeRunState:
    """Same-run result store for Python DAG nodes."""

    results_by_function: dict[object, PythonNodeExecutionResult] = field(default_factory=dict)

    def record_result(
        self,
        *,
        node_function: Callable[..., object],
        result: PythonNodeExecutionResult,
    ) -> None:
        self.results_by_function[node_function] = result
        self.results_by_function[("name", result.node_name)] = result

    def payload(
        self,
        node_function: Callable[..., object],
        *,
        default: object = MISSING_DEFAULT,
    ) -> object:
        result: PythonNodeExecutionResult | None = self.results_by_function.get(
            node_function
        ) or self.results_by_function.get(self._dependency_key(node_function))
        if result is None:
            if default is not MISSING_DEFAULT:
                return default
            raise ExecutorInputError("No same-run payload found for Python node")
        if result.status != PythonNodeStatus.SUCCESS:
            if default is not MISSING_DEFAULT:
                return default
            raise ExecutorInputError(
                f"Python node '{result.node_name}' did not produce a successful payload"
            )
        return result.payload

    def metadata(
        self,
        node_function: Callable[..., object],
        *,
        default: object = MISSING_DEFAULT,
    ) -> dict[str, object] | object:
        result: PythonNodeExecutionResult | None = self.results_by_function.get(
            node_function
        ) or self.results_by_function.get(self._dependency_key(node_function))
        if result is None:
            if default is not MISSING_DEFAULT:
                return default
            raise ExecutorInputError("No same-run metadata found for Python node")
        if result.status != PythonNodeStatus.SUCCESS:
            if default is not MISSING_DEFAULT:
                return default
            raise ExecutorInputError(
                f"Python node '{result.node_name}' did not produce successful metadata"
            )
        return result.metadata

    def _dependency_key(self, node_function: Callable[..., object]) -> object | tuple[str, str]:
        definition: object = getattr(node_function, "__sqlbuild_task__", None) or getattr(
            node_function, "__sqlbuild_asset__", None
        )
        name: object = getattr(definition, "name", None)
        if isinstance(name, str):
            return ("name", name)
        return node_function


@dataclass(frozen=True)
class PythonNodeExecutorResult:
    """Result bundle for one in-process Python-node executor run."""

    results: tuple[PythonNodeExecutionResult, ...]
    run_state: PythonNodeRunState


@dataclass(frozen=True)
class PythonIngressLoaderExecutorResult:
    """Result bundle for pre-SQL Python/loader lifecycle execution."""

    python_results: tuple[PythonNodeExecutionResult, ...]
    load_results: tuple[LoadExecutionResult, ...]
    run_state: PythonNodeRunState


@dataclass(frozen=True, kw_only=True)
class BasePythonNodeContext:
    """Shared runtime helpers for framework-owned Python nodes."""

    adapter: BaseAdapter
    connection_config: dict[str, object]
    connection: Any
    run_id: str
    target: str | None
    vars: dict[str, object]
    is_reload: bool
    logger: logging.Logger
    statement_recorder: StatementRecorder
    run_state: PythonNodeRunState | None = None
    default_database: str | None = None
    default_schema: str | None = None
    relation_targets: dict[SqlResourceRef, str] = field(default_factory=dict)
    allowed_sql_refs: frozenset[SqlResourceRef] = frozenset()
    use_color: bool = False
    start_cursor_ts: datetime | None = None
    end_cursor_ts: datetime | None = None
    start_cursor_int: int | None = None
    end_cursor_int: int | None = None

    def execute_sql(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def query(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def log(self, message: str) -> None:
        self.statement_recorder.log(message)
        self.logger.info(message)

    def qualify_name(
        self,
        name: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> str:
        """Return a qualified relation name, preserving already-qualified input."""

        if "." in name:
            return name
        return resolve_qualified_name_parts(
            adapter=self.adapter,
            database=self.default_database if database is None else database,
            schema=self.default_schema if schema is None else schema,
            name=name,
        )

    def relation(self, ref: SqlResourceRef) -> str:
        """Return the adapter-qualified runtime relation for a declared SQL ref."""

        if ref not in self.allowed_sql_refs:
            raise ExecutorInputError(
                f"SQL relation ref '{ref.name}' must be declared in depends_on before use"
            )
        relation: str | None = self.relation_targets.get(ref)
        if relation is None:
            raise ExecutorInputError(f"No runtime relation found for SQL ref '{ref.name}'")
        return relation

    def skip(
        self,
        reason: str,
        *,
        mode: SkipMode | str = SkipMode.SOFT,
        metadata: dict[str, object] | None = None,
    ) -> PythonNodeSkipResult:
        """Return a skip signal for the current Python node."""

        return PythonNodeSkipResult(
            reason=reason,
            mode=SkipMode(mode),
            metadata={} if metadata is None else metadata,
        )

    def payload(
        self,
        node_function: Callable[..., object],
        *,
        default: object = MISSING_DEFAULT,
    ) -> object:
        """Return a same-run upstream payload by Python node function reference."""

        if self.run_state is None:
            if default is not MISSING_DEFAULT:
                return default
            raise ExecutorInputError("No Python node run state is available")
        return self.run_state.payload(node_function, default=default)

    def metadata(
        self,
        node_function: Callable[..., object],
        *,
        default: object = MISSING_DEFAULT,
    ) -> dict[str, object] | object:
        """Return same-run upstream metadata by Python node function reference."""

        if self.run_state is None:
            if default is not MISSING_DEFAULT:
                return default
            raise ExecutorInputError("No Python node run state is available")
        return self.run_state.metadata(node_function, default=default)


@dataclass(frozen=True, kw_only=True)
class TaskContext(BasePythonNodeContext):
    """Runtime context passed to a SQLBuild task function."""

    def result(
        self,
        payload: object | None = None,
        *,
        metadata: dict[str, object] | None = None,
    ) -> PythonNodeResult:
        """Return a successful task result."""

        return PythonNodeResult(
            payload=payload,
            metadata={} if metadata is None else metadata,
        )


@dataclass(frozen=True, kw_only=True)
class AssetContext(BasePythonNodeContext):
    """Runtime context passed to a SQLBuild asset function."""

    def result(
        self,
        payload: object | None = None,
        *,
        metadata: dict[str, object] | None = None,
        materialized: bool | None = None,
    ) -> PythonNodeResult:
        """Return a successful asset result."""

        return PythonNodeResult(
            payload=payload,
            metadata={} if metadata is None else metadata,
            materialized=materialized,
        )


@dataclass(frozen=True, kw_only=True)
class CheckContext(BasePythonNodeContext):
    """Runtime context passed to a SQLBuild check function."""

    def pass_(
        self,
        message: str | None = None,
        *,
        metadata: dict[str, object] | None = None,
    ) -> PythonCheckResult:
        """Return a passing check result."""

        return PythonCheckResult(
            passed=True,
            message=message,
            metadata={} if metadata is None else metadata,
        )

    def fail(
        self,
        message: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> PythonCheckResult:
        """Return a failing check result using the check's configured severity."""

        return PythonCheckResult(
            passed=False,
            message=message,
            metadata={} if metadata is None else metadata,
        )

    def warn(
        self,
        message: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> PythonCheckResult:
        """Return a warning check result regardless of decorator severity."""

        return PythonCheckResult(
            passed=False,
            message=message,
            metadata={} if metadata is None else metadata,
            severity=PythonCheckSeverity.WARN,
        )
