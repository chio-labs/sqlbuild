"""Public Python-node selector entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.python_nodes._helpers.selectors import resolve_python_node_selectors
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph


def resolve_python_nodes_from_selectors(
    *, select: tuple[str, ...], exclude: tuple[str, ...], graph: PythonNodeGraph
) -> frozenset[str]:
    """Resolve raw selector strings into Python-node names."""

    return resolve_python_node_selectors(select=select, exclude=exclude, graph=graph)
