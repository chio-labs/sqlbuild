"""Destination and staging identifier resolution for table models."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.planner.main.scenarios.fit_artifact_logical_name import (
    fit_artifact_logical_name,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.run._helpers.execution.permanent_promotion import (
    permanent_model_identity,
)
from sqlbuild.executor.run.models import TableTargets


def resolve_table_targets(*, adapter: BaseAdapter, entry: ModelPlanEntry) -> TableTargets:
    """Resolve destination and staging identifiers for one table model."""

    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_table: str = entry.destination.name
    if entry.permanent_table:
        staging_prefix: str = "__sqb_staging__"
        fitted_staging_name: str = fit_artifact_logical_name(
            logical_name=f"{target_table}__{permanent_model_identity(entry)[:16]}",
            fixed_prefix=staging_prefix,
            identifier_limit=adapter.maximum_identifier_length(),
            artifact_label="Permanent staging",
        )
        staging_table = f"{staging_prefix}{fitted_staging_name}"
    else:
        staging_table = f"{target_table}__staging"
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
