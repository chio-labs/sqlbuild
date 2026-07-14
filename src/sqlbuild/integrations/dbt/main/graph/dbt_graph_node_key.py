"""Build a neutral dbt graph node key."""

from sqlbuild.compiler.planner.models import GraphNodeKey
from sqlbuild.integrations.dbt._helpers.planning.graph_projection import (
    dbt_graph_node_key as _build,
)


def dbt_graph_node_key(unique_id: str) -> GraphNodeKey:
    """Return a neutral planner key for a dbt node."""

    return _build(unique_id)
