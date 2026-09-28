"""The single owner of which relation names count as project relations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlbuild.compiler.compile.constants import MIGRATE_FROM_CONFIG_KEY
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.migrations.main._resolve_old_name_view_retention import (
    resolve_old_name_view_retention,
)
from sqlbuild.compiler.references._helpers.relation_names import (
    extract_relation_names_impl,
    match_project_relation_impl,
)
from sqlbuild.compiler.references.models import ProjectRelation, ProjectRelationIndex, RelationName
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry

_SCHEMA_QUALIFIED_PARTS: int = 2


def build_project_relation_index_impl(
    relations: Iterable[ProjectRelation],
) -> ProjectRelationIndex:
    """Return the deduplicated project-relation index for hard-coded name checks."""

    return ProjectRelationIndex(relations=tuple(dict.fromkeys(relations)))


def compiled_project_relations_impl(
    *, project: CompiledProject, old_name_retention: str | None
) -> ProjectRelationIndex:
    """Return the project relations a compiled project declares, with declared old names."""

    relations: list[ProjectRelation] = [
        _location_relation(
            ref=SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=model.name),
            location=model.destination,
        )
        for model in project.models
    ]
    relations.extend(
        _location_relation(
            ref=SqlResourceRef(kind=SqlResourceRefKind.SEED, name=seed.name),
            location=seed.destination,
        )
        for seed in project.seeds
    )
    for source in project.sources:
        entry: SourceEntry = source.source_entry
        if entry.expression is not None:
            continue
        relations.append(
            ProjectRelation(
                ref=SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=source.name),
                relation=RelationName(
                    name=entry.table or entry.name, schema=entry.schema, database=entry.database
                ),
            )
        )
    declared: ProjectRelationIndex = build_project_relation_index_impl(relations)
    return build_project_relation_index_impl(
        (
            *declared.relations,
            *_declared_old_names(
                project=project, declared=declared, old_name_retention=old_name_retention
            ),
        )
    )


def _declared_old_names(
    *, project: CompiledProject, declared: ProjectRelationIndex, old_name_retention: str | None
) -> tuple[ProjectRelation, ...]:
    """Return old names that migrate_from declarations keep only as compatibility views."""

    model_names: frozenset[str] = frozenset(model.name for model in project.models)
    old_names: list[ProjectRelation] = []
    model: CompiledModel
    for model in project.models:
        raw: object = model.config.values.get(MIGRATE_FROM_CONFIG_KEY)
        if not isinstance(raw, str) or (
            resolve_old_name_view_retention(
                config_values=model.config.values, project_retention=old_name_retention
            )
            is None
        ):
            continue
        parts: list[str] = [part.strip().strip('"`') for part in raw.split(".")]
        if len(parts) == 1 and parts[0] in model_names:
            continue
        relation: RelationName = RelationName(
            name=parts[-1],
            schema=parts[-2] if len(parts) > 1 else model.destination.schema,
            database=parts[-3]
            if len(parts) > _SCHEMA_QUALIFIED_PARTS
            else model.destination.database,
        )
        if (
            match_project_relation_impl(
                index=declared, relation=relation, default_database=None, default_schema=None
            )
            is not None
        ):
            continue
        old_names.append(
            ProjectRelation(
                ref=SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=model.name),
                relation=relation,
                compatibility_for=model.name,
            )
        )
    return tuple(old_names)


def runtime_project_relations_impl(
    *, relations: Mapping[SqlResourceRef, str], dialect: str | None
) -> ProjectRelationIndex:
    """Return project relations from adapter-rendered runtime relation names."""

    resolved: list[ProjectRelation] = []
    for ref, qualified in relations.items():
        extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None = (
            extract_relation_names_impl(sql=f"SELECT 1 FROM {qualified}", dialect=dialect)
        )
        if extracted is None or len(extracted[0]) != 1:
            continue
        resolved.append(ProjectRelation(ref=ref, relation=extracted[0][0]))
    return build_project_relation_index_impl(resolved)


def _location_relation(
    *, ref: SqlResourceRef, location: CompiledRelationLocation
) -> ProjectRelation:
    return ProjectRelation(
        ref=ref,
        relation=RelationName(
            name=location.name, schema=location.schema, database=location.database
        ),
    )
