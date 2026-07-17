"""Build a dbt model graph key."""

from sqlbuild.integrations.dbt._helpers.graph.core import dbt_model_graph_key as _build
from sqlbuild.integrations.dbt.models import DbtCombinedGraphKey


def dbt_model_graph_key(unique_id: str) -> DbtCombinedGraphKey:
    """Return the combined graph key for a dbt model."""

    return _build(unique_id)
