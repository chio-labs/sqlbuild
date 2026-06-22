"""Public entrypoints for neutral graph identity resolution."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.compiler.planner.helpers.graph_identity import (
    build_expected_graph_identity_hashes as _build_expected_graph_identity_hashes,
)
from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey


def build_expected_graph_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    compose_identity: Callable[[str, tuple[tuple[GraphNodeKey, str], ...]], str],
) -> dict[GraphNodeKey, str | None]:
    """Build expected identity hashes for a neutral dependency graph."""

    return _build_expected_graph_identity_hashes(
        nodes=nodes,
        execution_order=execution_order,
        compose_identity=compose_identity,
    )
