"""Build a neutral SQLBuild model graph key."""

from sqlbuild.compiler.planner.models import GraphNodeKey
from sqlbuild.integrations.dbt.helpers.planning.graph_projection import (
    sqlbuild_model_graph_node_key as _build,
)


def sqlbuild_model_graph_node_key(name: str) -> GraphNodeKey:
    """Return a neutral planner key for a SQLBuild model."""

    return _build(name)
