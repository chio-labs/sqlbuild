"""Execution graph concurrency sizing."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import PlanOutput


def runnable_graph_width(*, plan: PlanOutput) -> int:
    """Return a safe worker cap that cannot underestimate asynchronous overlap."""

    executable_node_count: int = len(plan.execution_order)
    return max(1, executable_node_count)
