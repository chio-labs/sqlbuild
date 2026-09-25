"""Fresh stage and displaced-destination names for one migration attempt."""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.janitor.main._build_archive_name import build_janitor_archive_name
from sqlbuild.executor.migrations.constants import (
    MIGRATION_NAME_ATTEMPTS,
    MIGRATION_PREVIOUS_ARCHIVE_KIND,
    MIGRATION_STAGE_ARCHIVE_KIND,
)
from sqlbuild.executor.migrations.models import MigrationArtifactNames


def resolve_artifact_names(
    *, adapter: BaseAdapter, connection: Any, entry: ModelMigrationPlanEntry, now: datetime
) -> MigrationArtifactNames:
    """Pick the latest second at or before now, never later, whose archive names are unused."""

    schema: str | None = entry.destination.schema
    if schema is None:
        raise ExecutorInputError(
            f"model '{entry.model_name}': model migrations require a destination schema"
        )
    database: str | None = entry.destination.database
    identifier_limit: int = adapter.maximum_identifier_length()
    candidates: tuple[tuple[str, str], ...] = tuple(
        (
            build_janitor_archive_name(
                original_name=entry.destination.name,
                archived_at=now - timedelta(seconds=offset),
                identifier_limit=identifier_limit,
                kind=MIGRATION_STAGE_ARCHIVE_KIND,
            ),
            build_janitor_archive_name(
                original_name=entry.destination.name,
                archived_at=now - timedelta(seconds=offset),
                identifier_limit=identifier_limit,
                kind=MIGRATION_PREVIOUS_ARCHIVE_KIND,
            ),
        )
        for offset in range(MIGRATION_NAME_ATTEMPTS)
    )
    listed: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=database,
        schemas=(schema,),
        names=(entry.destination.name, *itertools.chain.from_iterable(candidates)),
    )
    existing: frozenset[str] = frozenset(
        relation.name.lower()
        for relation in listed
        if (relation.schema or "").lower() == schema.lower()
    )
    stage_name: str
    displaced_name: str
    for stage_name, displaced_name in candidates:
        if stage_name not in existing and displaced_name not in existing:
            return MigrationArtifactNames(
                stage_name=stage_name,
                stage_qualified=resolve_qualified_name_parts(
                    adapter=adapter, database=database, schema=schema, name=stage_name
                ),
                displaced_name=displaced_name,
                displaced_qualified=resolve_qualified_name_parts(
                    adapter=adapter, database=database, schema=schema, name=displaced_name
                ),
                destination_qualified=resolve_qualified_name_parts(
                    adapter=adapter, database=database, schema=schema, name=entry.destination.name
                ),
                destination_exists=entry.destination.name.lower() in existing,
            )
    raise ExecutorInputError(
        f"model '{entry.model_name}': no unused migration stage name was found in the last "
        f"{MIGRATION_NAME_ATTEMPTS} seconds"
    )
