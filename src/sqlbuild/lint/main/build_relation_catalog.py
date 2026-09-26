"""Publish compiler-owned relation columns for bound SQL Rule analysis."""

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.lint.types import LintRelationCatalog


def build_relation_catalog(*, project: CompiledProject) -> LintRelationCatalog:
    columns: LintRelationCatalog = {}
    for model in project.models:
        if model.inferred_columns is not None:
            columns[("ref", model.name, None)] = tuple(
                column.name for column in model.inferred_columns
            )
    for source in project.sources:
        columns[("source", source.name, None)] = tuple(
            column.name for column in source.source_entry.columns
        )
    for seed in project.seeds:
        columns[("seed", seed.name, None)] = tuple(
            column.name for column in seed.schema_entry.columns
        )
    return columns
