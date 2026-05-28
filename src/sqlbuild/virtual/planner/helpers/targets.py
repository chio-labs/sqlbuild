"""Virtual planner target helpers."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def build_target_from_physical_relation(
    *,
    adapter: BaseAdapter,
    relation: PhysicalRelationRecord,
    fallback_target: CompiledRelationTarget,
) -> CompiledRelationTarget:
    """Rebuild a compiled target from a stored physical relation record."""

    return CompiledRelationTarget(
        database=relation.database_name,
        schema=relation.schema_name,
        name=relation.relation_name,
        qualified_name=adapter.render_qualified_name(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        ),
        logical_schema=fallback_target.logical_schema,
        logical_database=fallback_target.logical_database,
    )
