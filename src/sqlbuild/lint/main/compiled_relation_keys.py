"""Declared unique keys of a compiled project's relations."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.lint.main.declared_relation_keys import declared_relation_keys
from sqlbuild.lint.types import RelationKeys


def compiled_relation_keys(project: CompiledProjectView) -> RelationKeys:
    """Collect declared keys of compiled models, seeds and sources."""

    return declared_relation_keys(
        model_rows=(model.relation_key_row for model in project.models),
        seeds=(seed.schema_entry for seed in project.seeds),
        sources=(source.source_entry for source in project.sources),
    )
