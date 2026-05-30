"""Helpers for Python-node scheduler tests."""

from __future__ import annotations

from sqlbuild.executor.shared.helpers.python_node_scheduler import unlock_downstream_python_nodes


def apply_completion_order(
    *,
    completion_order: tuple[str, ...],
    in_degree: dict[str, int],
    ready: list[str],
    downstream_names: dict[str, tuple[str, ...]],
) -> None:
    completed_node_name: str
    for completed_node_name in completion_order:
        unlock_downstream_python_nodes(
            completed_node_name=completed_node_name,
            in_degree=in_degree,
            ready=ready,
            downstream_names=downstream_names,
        )
