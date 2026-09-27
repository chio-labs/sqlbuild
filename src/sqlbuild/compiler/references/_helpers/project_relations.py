"""The single owner of which relation names count as project relations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.references._helpers.relation_names import extract_relation_names_impl
from sqlbuild.compiler.references.models import ProjectRelation, ProjectRelationIndex, RelationName
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry


def build_project_relation_index_impl(
    relations: Iterable[ProjectRelation],
) -> ProjectRelationIndex:
    """Return the deduplicated project-relation index for hard-coded name checks."""

    return ProjectRelationIndex(relations=tuple(dict.fromkeys(relations)))


def compiled_project_relations_impl(project: CompiledProject) -> ProjectRelationIndex:
    """Return the project relations a compiled project declares."""

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
    return build_project_relation_index_impl(relations)


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
