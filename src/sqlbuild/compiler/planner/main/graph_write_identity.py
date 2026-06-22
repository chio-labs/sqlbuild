"""Public entrypoint for neutral graph write identity resolution."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.compiler.planner.helpers.identity.graph import (
    build_graph_write_identity_hashes as _build_graph_write_identity_hashes,
)
from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey


def build_graph_write_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    selected_keys: frozenset[GraphNodeKey],
    base_identity_hashes: Mapping[GraphNodeKey, str],
    compose_identity: Callable[[str, tuple[tuple[GraphNodeKey, str], ...]], str],
) -> dict[GraphNodeKey, str]:
    """Build write identity hashes from caller-supplied available upstream hashes."""

    return _build_graph_write_identity_hashes(
        nodes=nodes,
        execution_order=execution_order,
        selected_keys=selected_keys,
        base_identity_hashes=base_identity_hashes,
        compose_identity=compose_identity,
    )
