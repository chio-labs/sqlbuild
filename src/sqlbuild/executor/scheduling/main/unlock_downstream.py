"""Public operation for unlocking downstream DAG nodes."""

from __future__ import annotations

from sqlbuild.executor.scheduling.helpers.python_nodes import (
    unlock_downstream_python_nodes as _unlock_downstream_python_nodes,
)


def unlock_downstream_python_nodes(
    *,
    completed_node_name: str,
    in_degree: dict[str, int],
    downstream_names: dict[str, tuple[str, ...]],
) -> tuple[dict[str, int], tuple[str, ...]]:
    """Return updated in-degrees and newly ready nodes after one completion."""

    return _unlock_downstream_python_nodes(
        completed_node_name=completed_node_name,
        in_degree=in_degree,
        downstream_names=downstream_names,
    )
