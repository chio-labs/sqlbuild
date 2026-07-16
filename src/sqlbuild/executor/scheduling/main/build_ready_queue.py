"""Public operation for building a DAG ready queue."""

from __future__ import annotations

from sqlbuild.executor.scheduling._helpers.python_nodes import (
    build_python_node_ready_queue as _build_python_node_ready_queue,
)


def build_python_node_ready_queue(
    *, node_names: tuple[str, ...], in_degree: dict[str, int]
) -> list[str]:
    """Return nodes with no unresolved dependencies in input order."""

    return _build_python_node_ready_queue(node_names=node_names, in_degree=in_degree)
