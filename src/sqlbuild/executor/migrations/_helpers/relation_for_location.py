"""Name compiled relation locations in migration events."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.models import MigrationRelation


def migration_relation_for_location(location: CompiledRelationLocation) -> MigrationRelation:
    """Return the migration relation that names one compiled relation location."""

    return MigrationRelation(database=location.database, schema=location.schema, name=location.name)
