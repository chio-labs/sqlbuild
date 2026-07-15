"""Build dbt model planning results."""

from collections.abc import Sequence
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.integrations.dbt._helpers.planning.model_planning import (
    build_dbt_model_planning_result as _build,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtManifestIndex,
    DbtModelPlanningResult,
)


def build_dbt_model_planning_result(
    *,
    manifest: DbtManifestIndex,
    candidate_unique_ids: Sequence[str],
    selected_unique_ids: Sequence[str] | None = None,
    project: CompiledProject,
    graph: DbtCombinedGraph | None = None,
    full_refresh: bool = False,
    force: bool = False,
    adapter: BaseAdapter,
    connection: Any,
) -> DbtModelPlanningResult:
    """Classify dbt model candidates from state and relations."""

    return _build(
        manifest=manifest,
        candidate_unique_ids=candidate_unique_ids,
        selected_unique_ids=selected_unique_ids,
        project=project,
        graph=graph,
        full_refresh=full_refresh,
        force=force,
        adapter=adapter,
        connection=connection,
    )
