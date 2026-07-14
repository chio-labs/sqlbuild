"""Build a SQLBuild model graph key."""

from sqlbuild.integrations.dbt.helpers.graph.core import sqlbuild_model_graph_key as _build
from sqlbuild.integrations.dbt.models import DbtCombinedGraphKey


def sqlbuild_model_graph_key(model_name: str) -> DbtCombinedGraphKey:
    """Return the combined graph key for a SQLBuild model."""

    return _build(model_name)
