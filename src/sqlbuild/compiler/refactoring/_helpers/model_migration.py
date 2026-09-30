"""Decide whether a renamed or moved model needs an explicit migrate_from."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.planner.classes.migration_fingerprint_cache import (
    MigrationFingerprintCache,
)
from sqlbuild.compiler.planner.main.identity.version_identity_function_hashes import (
    build_function_local_hashes,
)
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from sqlbuild.compiler.python_nodes.main.hook_identities import build_hook_identities
from sqlbuild.compiler.refactoring.constants import (
    HISTORY_MATERIALIZATIONS,
    MATERIALIZED_KEY,
    MIGRATABLE_MATERIALIZATIONS,
    MIGRATE_FROM_KEY,
)
from sqlbuild.compiler.refactoring.models import ModelMigrationDecision
from sqlbuild.spec.contracts.main.get_config_str import get_config_str


def decide_model_migration(
    *, before: CompiledProject, after: CompiledProject, old: str, new: str
) -> ModelMigrationDecision:
    """Compare the old and new compile the way automatic rename discovery would."""

    old_model: CompiledModel | None = _model(project=before, name=old)
    new_model: CompiledModel | None = _model(project=after, name=new)
    if old_model is None or new_model is None:
        return ModelMigrationDecision(needed=False, reason="model not compiled")
    materialized: str | None = get_config_str(values=new_model.config.values, key=MATERIALIZED_KEY)
    if materialized not in MIGRATABLE_MATERIALIZATIONS:
        return ModelMigrationDecision(
            needed=False, reason=f"'{materialized}' models have no migration"
        )
    if _location_key(old_model) == _location_key(new_model):
        return ModelMigrationDecision(needed=False, reason="relation name is unchanged")
    old_database: str = (old_model.destination.database or "").lower()
    new_database: str = (new_model.destination.database or "").lower()
    if old_database and new_database and old_database != new_database:
        return ModelMigrationDecision(
            needed=False,
            blocked=True,
            reason=(
                f"moves from database {old_model.destination.database} to "
                f"{new_model.destination.database}; migrations cannot cross databases"
            ),
        )
    old_schema: str = (old_model.destination.schema or "").lower()
    project_schemas: frozenset[str] = frozenset(
        (model.destination.schema or "").lower() for model in after.models
    )
    if old_schema not in project_schemas:
        return ModelMigrationDecision(
            needed=False,
            blocked=True,
            reason=(
                f"no model is left in schema {old_model.destination.schema}, so neither "
                f"automatic discovery nor migrate_from {old} can find the old relation; add a "
                "schema-qualified migrate_from for each target"
            ),
        )
    old_materialized: str | None = get_config_str(
        values=old_model.config.values, key=MATERIALIZED_KEY
    )
    if (old_materialized in HISTORY_MATERIALIZATIONS) != (materialized in HISTORY_MATERIALIZATIONS):
        return ModelMigrationDecision(
            needed=True, reason=f"materialization changes from {old_materialized}"
        )
    before_fingerprint: str | None = _fingerprint(project=before, model=old_model)
    after_fingerprint: str | None = _fingerprint(project=after, model=new_model)
    if before_fingerprint is None:
        return ModelMigrationDecision(
            needed=True,
            reason="automatic discovery cannot fingerprint its SQL, so it would not find the "
            "old relation",
        )
    if before_fingerprint != after_fingerprint:
        return ModelMigrationDecision(
            needed=True,
            reason="its definition changes at the new location, so automatic discovery "
            "cannot match it",
        )
    return ModelMigrationDecision(
        needed=False, reason="automatic rename discovery matches the unchanged definition"
    )


def needs_column_migration(*, model: CompiledModel) -> bool:
    """Return whether renaming a column of this model must declare migrate_from."""

    materialized: str | None = get_config_str(values=model.config.values, key=MATERIALIZED_KEY)
    if materialized in HISTORY_MATERIALIZATIONS:
        return True
    return (
        materialized in MIGRATABLE_MATERIALIZATIONS
        and model.config.values.get(MIGRATE_FROM_KEY) is not None
    )


def _fingerprint(*, project: CompiledProject, model: CompiledModel) -> str | None:
    metadata_json: str = build_model_version_identity_metadata_json(
        model=model,
        function_local_hashes=build_function_local_hashes(functions=project.functions),
        hook_version_hashes={
            name: identity.version_hash
            for name, identity in build_hook_identities(project.hook_functions).items()
        },
    )
    return MigrationFingerprintCache().fingerprint(
        query_sql=model.query_sql,
        metadata_json=metadata_json,
        ref_identities={},
        dialect=project.sql_analysis_dialect,
    )


def _model(*, project: CompiledProject, name: str) -> CompiledModel | None:
    return next((model for model in project.models if model.name == name), None)


def _location_key(model: CompiledModel) -> tuple[str, str, str]:
    return (
        (model.destination.database or "").lower(),
        (model.destination.schema or "").lower(),
        model.destination.name.lower(),
    )
