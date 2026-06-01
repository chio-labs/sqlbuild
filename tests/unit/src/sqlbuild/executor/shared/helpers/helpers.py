"""Helpers for shared executor helper tests."""

from __future__ import annotations

from sqlbuild.executor.shared.models.lifecycle_scheduler import (
    LifecycleExecutionNode,
    LifecycleNodeResult,
)
from sqlbuild.executor.shared.types import LifecycleNodeStatus


def record_lifecycle_success(
    *, node: LifecycleExecutionNode, calls: list[str]
) -> LifecycleNodeResult:
    calls.append(node.name)
    return lifecycle_success(node)


def record_lifecycle_maybe_failure(
    *, node: LifecycleExecutionNode, calls: list[str]
) -> LifecycleNodeResult:
    calls.append(node.name)
    if node.name == "summarize_pages":
        return LifecycleNodeResult(
            name=node.name,
            kind=node.kind,
            status=LifecycleNodeStatus.FAILED,
            error_message="failed",
        )
    return lifecycle_success(node)


def lifecycle_success(node: LifecycleExecutionNode) -> LifecycleNodeResult:
    return LifecycleNodeResult(
        name=node.name,
        kind=node.kind,
        status=LifecycleNodeStatus.SUCCESS,
    )
