"""Result normalization and fan-in policy helpers for Python DAG nodes."""

from __future__ import annotations

from sqlbuild.compiler.python_nodes.types import (
    PythonNodeFanInAction,
    PythonNodeKind,
    PythonNodeStatus,
    SkipMode,
)
from sqlbuild.executor.python_nodes.models import (
    PythonNodeExecutionResult,
    PythonNodeFanInDecision,
    PythonNodeResult,
    PythonNodeSkipResult,
)
from sqlbuild.executor.shared.exceptions import ExecutorInputError


def normalize_python_node_return(
    *,
    node_name: str,
    kind: PythonNodeKind,
    returned: object,
) -> PythonNodeExecutionResult:
    """Normalize a raw Python-node return value into an execution result."""

    if isinstance(returned, PythonNodeSkipResult):
        return PythonNodeExecutionResult(
            node_name=node_name,
            kind=kind,
            status=PythonNodeStatus.SKIPPED,
            metadata=returned.metadata,
            skip_mode=returned.mode,
            skip_reason=returned.reason,
        )
    if isinstance(returned, PythonNodeResult):
        _validate_materialized_flag(kind=kind, materialized=returned.materialized)
        return PythonNodeExecutionResult(
            node_name=node_name,
            kind=kind,
            status=PythonNodeStatus.SUCCESS,
            payload=returned.payload,
            metadata=returned.metadata,
            materialized=returned.materialized,
        )
    return PythonNodeExecutionResult(
        node_name=node_name,
        kind=kind,
        status=PythonNodeStatus.SUCCESS,
        payload=returned,
    )


def build_python_node_failure_result(
    *,
    node_name: str,
    kind: PythonNodeKind,
    error: BaseException,
) -> PythonNodeExecutionResult:
    """Normalize an exception into a failed Python-node execution result."""

    return PythonNodeExecutionResult(
        node_name=node_name,
        kind=kind,
        status=PythonNodeStatus.FAILED,
        error_message=str(error),
    )


def evaluate_python_node_fan_in(
    *, upstream_results: tuple[PythonNodeExecutionResult, ...]
) -> PythonNodeFanInDecision:
    """Return whether a node can run, should skip, or is blocked by upstream outcomes."""

    if not upstream_results:
        return PythonNodeFanInDecision(action=PythonNodeFanInAction.RUN)
    failed_names: tuple[str, ...] = tuple(
        result.node_name for result in upstream_results if result.status == PythonNodeStatus.FAILED
    )
    if failed_names:
        return PythonNodeFanInDecision(
            action=PythonNodeFanInAction.BLOCK,
            reason=f"Upstream Python node failed: {', '.join(failed_names)}",
        )
    hard_skipped_names: tuple[str, ...] = tuple(
        result.node_name
        for result in upstream_results
        if result.status == PythonNodeStatus.SKIPPED and result.skip_mode == SkipMode.DOWNSTREAM
    )
    if hard_skipped_names:
        return PythonNodeFanInDecision(
            action=PythonNodeFanInAction.SKIP,
            reason=f"Upstream Python node skipped downstream: {', '.join(hard_skipped_names)}",
        )
    if any(result.status == PythonNodeStatus.SUCCESS for result in upstream_results):
        return PythonNodeFanInDecision(action=PythonNodeFanInAction.RUN)
    return PythonNodeFanInDecision(
        action=PythonNodeFanInAction.SKIP,
        reason="All upstream Python nodes were skipped",
    )


def _validate_materialized_flag(*, kind: PythonNodeKind, materialized: bool | None) -> None:
    if materialized is not None and kind != PythonNodeKind.ASSET:
        raise ExecutorInputError("Only asset Python nodes may set materialized")
