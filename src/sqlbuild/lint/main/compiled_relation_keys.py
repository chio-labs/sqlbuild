"""Declared unique keys of a compiled project's relations."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.lint.constants import RELATION_KIND_REF, RELATION_KIND_SEED, RELATION_KIND_SOURCE
from sqlbuild.lint.main.declared_relation_keys import declared_relation_keys
from sqlbuild.lint.types import RelationKeys


def compiled_relation_keys(project: CompiledProject) -> RelationKeys:
    """Collect declared keys of compiled models, seeds and sources."""

    return declared_relation_keys(
        relations=(
            *(
                (RELATION_KIND_REF, model.name, model.schema_entry, model.config.values)
                for model in project.models
            ),
            *((RELATION_KIND_SEED, seed.name, seed.schema_entry, {}) for seed in project.seeds),
            *(
                (RELATION_KIND_SOURCE, source.name, source.source_entry, {})
                for source in project.sources
            ),
        )
    )
