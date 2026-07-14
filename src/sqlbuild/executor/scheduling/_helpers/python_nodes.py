"""Generic ready-queue scheduling helpers for Python DAG nodes."""

from __future__ import annotations


def build_python_node_in_degree(
    *, node_names: tuple[str, ...], upstream_names: dict[str, tuple[str, ...]]
) -> dict[str, int]:
    """Return the unresolved dependency count for each node."""

    return {node_name: len(upstream_names[node_name]) for node_name in node_names}


def build_python_node_ready_queue(
    *, node_names: tuple[str, ...], in_degree: dict[str, int]
) -> list[str]:
    """Return nodes with no unresolved dependencies in input order."""

    return [node_name for node_name in node_names if in_degree[node_name] == 0]


def unlock_downstream_python_nodes(
    *,
    completed_node_name: str,
    in_degree: dict[str, int],
    downstream_names: dict[str, tuple[str, ...]],
) -> tuple[dict[str, int], tuple[str, ...]]:
    """Return updated in-degrees and newly ready nodes after one completion."""

    updated_in_degree: dict[str, int] = dict(in_degree)
    newly_ready: list[str] = []
    downstream_name: str
    for downstream_name in downstream_names.get(completed_node_name, ()):
        updated_in_degree[downstream_name] = updated_in_degree.get(downstream_name, 1) - 1
        if updated_in_degree[downstream_name] == 0:
            newly_ready.append(downstream_name)
    return updated_in_degree, tuple(newly_ready)
