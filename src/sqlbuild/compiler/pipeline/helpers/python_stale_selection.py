"""Python-node selection pruning for stale-only planning."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.python_nodes.models import DiscoveredPythonNode, PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.shared.types import SqlResourceRefKind


def filter_python_node_names_for_selected_sql(
    *,
    python_graph: PythonNodeGraph,
    python_node_names: frozenset[str],
    selected_sql_keys: frozenset[CompiledObjectKey],
) -> frozenset[str]:
    """Drop read-side Python nodes whose selected SQL dependencies were pruned."""

    selected_sql_refs_set: set[SqlResourceRef] = set()
    key: CompiledObjectKey
    for key in selected_sql_keys:
        sql_ref: SqlResourceRef | None = _sql_ref_from_key(key)
        if sql_ref is not None:
            selected_sql_refs_set.add(sql_ref)
    selected_sql_refs: frozenset[SqlResourceRef] = frozenset(selected_sql_refs_set)
    kept: set[str] = set()
    node_name: str
    for node_name in python_node_names:
        node: DiscoveredPythonNode = python_graph.nodes_by_name[node_name]
        if node.kind == PythonNodeKind.LOADER:
            kept.add(node_name)
            continue
        if all(sql_dep in selected_sql_refs for sql_dep in node.sql_deps):
            kept.add(node_name)

    changed: bool = True
    while changed:
        changed = False
        for node_name in tuple(kept):
            upstream_name: str
            for upstream_name in python_graph.upstream_deps.get(node_name, ()):
                if upstream_name in python_node_names and upstream_name not in kept:
                    kept.remove(node_name)
                    changed = True
                    break
    return frozenset(kept)


def _sql_ref_from_key(key: CompiledObjectKey) -> SqlResourceRef | None:
    if key.resource_type == CompiledResourceType.MODEL:
        return SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=key.name)
    if key.resource_type == CompiledResourceType.SOURCE:
        return SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=key.name)
    return None
