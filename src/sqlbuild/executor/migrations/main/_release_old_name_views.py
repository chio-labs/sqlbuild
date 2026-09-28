"""Release compatibility views bound to a relation that is about to be rebuilt."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.migrations._helpers.old_name_views import drop_old_name_views, views_reading
from sqlbuild.executor.migrations.models import OldNameViewSource


def release_old_name_views(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    destination: CompiledRelationLocation,
) -> tuple[OldNameViewSource, ...]:
    """Drop views bound to the relation's identity so its rebuild can replace it."""

    if not adapter.views_bind_to_relation_identity():
        return ()
    released: tuple[OldNameViewSource, ...] = views_reading(
        location=destination, recorded_views=plan.old_name_views
    )
    _ = drop_old_name_views(adapter=adapter, connection=connection, sources=released)
    return released
