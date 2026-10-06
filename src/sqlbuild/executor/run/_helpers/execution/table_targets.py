"""Destination and staging identifier resolution for table models."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.main.fit_auxiliary_relation_name import fit_auxiliary_relation_name
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.run.constants import STAGING_RELATION_SUFFIX
from sqlbuild.executor.run.models import TableTargets


def resolve_table_targets(*, adapter: BaseAdapter, entry: ModelPlanEntry) -> TableTargets:
    """Resolve destination and staging identifiers for one table model."""

    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_table: str = entry.destination.name
    staging_table: str = fit_auxiliary_relation_name(
        base_name=target_table,
        suffix=STAGING_RELATION_SUFFIX,
        identifier_limit=adapter.maximum_identifier_length(),
    )
    return TableTargets(
        target_qualified=resolve_relation_location_qualified_name(
            adapter=adapter, location=entry.destination
        ),
        target_database=target_database,
        target_schema=target_schema,
        target_table=target_table,
        staging_qualified=resolve_qualified_name_parts(
            adapter=adapter,
            database=target_database,
            schema=target_schema,
            name=staging_table,
        ),
        staging_table=staging_table,
    )
