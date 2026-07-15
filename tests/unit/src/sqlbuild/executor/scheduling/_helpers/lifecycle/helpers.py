"""Helpers for lifecycle scheduler tests."""

from __future__ import annotations

from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.scheduling.models import (
    LifecycleExecutionNode,
    LifecycleNodeResult,
)
from sqlbuild.executor.scheduling.types import LifecycleNodeStatus


def record_lifecycle_success(
    *, node: LifecycleExecutionNode, calls: list[str]
) -> LifecycleNodeResult:
    calls.append(node.name)
    return lifecycle_success(node)


def record_lifecycle_maybe_failure(
    *, node: LifecycleExecutionNode, calls: list[str]
) -> LifecycleNodeResult:
    calls.append(node.name)
    return {"summarize_pages": lifecycle_failure}.get(node.name, lifecycle_success)(node)


def record_lifecycle_soft_skip_a_else_success(
    *, node: LifecycleExecutionNode, calls: list[str]
) -> LifecycleNodeResult:
    calls.append(node.name)
    return {"A": lifecycle_soft_skip}.get(node.name, lifecycle_success)(node)


def record_lifecycle_hard_skip_a_else_success(
    *, node: LifecycleExecutionNode, calls: list[str]
) -> LifecycleNodeResult:
    calls.append(node.name)
    return {"A": lifecycle_hard_skip}.get(node.name, lifecycle_success)(node)


def lifecycle_success(node: LifecycleExecutionNode) -> LifecycleNodeResult:
    return LifecycleNodeResult(
        name=node.name,
        kind=node.kind,
        status=LifecycleNodeStatus.SUCCESS,
    )


def lifecycle_failure(node: LifecycleExecutionNode) -> LifecycleNodeResult:
    return LifecycleNodeResult(
        name=node.name,
        kind=node.kind,
        status=LifecycleNodeStatus.FAILED,
        error_message="failed",
    )


def lifecycle_soft_skip(node: LifecycleExecutionNode) -> LifecycleNodeResult:
    return LifecycleNodeResult(
        name=node.name,
        kind=node.kind,
        status=LifecycleNodeStatus.SKIPPED,
        skip_reason="no work",
        skip_mode=SkipMode.SOFT,
    )


def lifecycle_hard_skip(node: LifecycleExecutionNode) -> LifecycleNodeResult:
    return LifecycleNodeResult(
        name=node.name,
        kind=node.kind,
        status=LifecycleNodeStatus.SKIPPED,
        skip_reason="blocked",
        skip_mode=SkipMode.HARD,
    )
