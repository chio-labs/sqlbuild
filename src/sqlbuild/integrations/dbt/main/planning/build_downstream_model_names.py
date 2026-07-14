"""Build downstream SQLBuild model names."""

from sqlbuild.integrations.dbt._helpers.planning.model_planning import (
    build_downstream_sqlbuild_model_names as _build,
)
from sqlbuild.integrations.dbt.models import DbtCombinedGraph


def build_downstream_sqlbuild_model_names(
    *, graph: DbtCombinedGraph | None, dbt_unique_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """Return SQLBuild models downstream of dbt nodes."""

    return _build(graph=graph, dbt_unique_ids=dbt_unique_ids)
