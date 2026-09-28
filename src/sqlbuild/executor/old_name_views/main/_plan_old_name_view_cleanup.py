"""Plan janitor cleanup of compatibility views at old model names."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.executor.janitor.models import JanitorOldNameViewPlanning, JanitorRelationScope
from sqlbuild.executor.old_name_views._helpers.janitor import (
    plan_old_name_views,
    project_destinations,
    protect_old_names,
)


def plan_old_name_view_cleanup(
    *,
    adapter: BaseAdapter,
    connection: Any,
    managed_target_schemas: set[tuple[str | None, str | None]],
    relations_by_schema: dict[tuple[str | None, str | None], tuple[RelationInfo, ...]],
    target_name: str | None,
    early_drops: tuple[str, ...],
    project: CompiledProject,
    scope: JanitorRelationScope,
    now: datetime,
) -> tuple[JanitorOldNameViewPlanning, JanitorRelationScope]:
    """Return old-name view actions and a scope that keeps general cleanup away from them."""

    old_names: JanitorOldNameViewPlanning = plan_old_name_views(
        adapter=adapter,
        connection=connection,
        managed_target_schemas=managed_target_schemas,
        relations_by_schema=relations_by_schema,
        target_name=target_name,
        early_drops=early_drops,
        project_destinations=project_destinations(project),
        now=now,
    )
    return old_names, protect_old_names(scope=scope, old_names=old_names)
