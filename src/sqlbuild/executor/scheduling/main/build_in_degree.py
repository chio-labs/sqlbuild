"""Public operation for building DAG in-degrees."""

from __future__ import annotations

from sqlbuild.executor.scheduling.helpers.python_nodes import (
    build_python_node_in_degree as _build_python_node_in_degree,
)


def build_python_node_in_degree(
    *, node_names: tuple[str, ...], upstream_names: dict[str, tuple[str, ...]]
) -> dict[str, int]:
    """Return the unresolved dependency count for each node."""

    return _build_python_node_in_degree(node_names=node_names, upstream_names=upstream_names)
