"""Attach the migration fingerprint each built model stores with its fingerprint row."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.planner.classes.migration_fingerprint_cache import (
    MigrationFingerprintCache,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import PlanAction


def with_migration_fingerprints(
    *,
    entries: tuple[ModelPlanEntry, ...],
    models_by_name: Mapping[str, CompiledModel],
    fingerprints: MigrationFingerprintCache,
    dialect: str | None,
) -> tuple[ModelPlanEntry, ...]:
    """Attach current-name migration fingerprints to the entries that will be built."""

    attached: list[ModelPlanEntry] = []
    entry: ModelPlanEntry
    for entry in entries:
        model: CompiledModel | None = models_by_name.get(entry.name)
        if (
            model is None
            or entry.fingerprint_metadata_json is None
            or entry.action == PlanAction.SKIP
        ):
            attached.append(entry)
            continue
        attached.append(
            replace(
                entry,
                migration_fingerprint=fingerprints.fingerprint(
                    query_sql=model.query_sql,
                    metadata_json=entry.fingerprint_metadata_json,
                    ref_identities={},
                    dialect=dialect,
                ),
            )
        )
    fingerprints.persist()
    return tuple(attached)
