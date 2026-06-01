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
    ready: list[str],
    downstream_names: dict[str, tuple[str, ...]],
) -> None:
    """Mark one node complete and append newly ready downstream nodes."""

    downstream_name: str
    for downstream_name in downstream_names.get(completed_node_name, ()):
        in_degree[downstream_name] = in_degree.get(downstream_name, 1) - 1
        if in_degree[downstream_name] == 0:
            ready.append(downstream_name)
