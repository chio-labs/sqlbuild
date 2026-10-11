"""The SQL and declared families Python's dynamic pivot proof reads for each model."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.compile._helpers.analysis.reference_names import (
    substitute_placeholder_defaults,
)
from sqlbuild.compiler.compile._helpers.analysis.syntax_checks import model_placeholders
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
)
from sqlbuild.compiler.compile.models import CompileModelInput, ModelSqlAnalysis
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def model_pivot_sql(*, query_sql: str, placeholders: dict[str, str] | None) -> str:
    """Return the analysis SQL with placeholder defaults, as the pivot proof parses it."""

    if not placeholders:
        return query_sql
    return substitute_placeholder_defaults(query_sql=query_sql, placeholders=placeholders)


def model_dynamic_families(model_input: CompileModelInput) -> tuple[SchemaDynamicColumnFamily, ...]:
    """Return the dynamic column families the model's schema declares."""

    if model_input.schema_entry is None:
        return ()
    return model_input.schema_entry.dynamic_columns


def standalone_pivot_models(
    *, model_inputs: tuple[CompileModelInput, ...], analyses: Mapping[str, ModelSqlAnalysis]
) -> dict[int, tuple[str, tuple[SchemaDynamicColumnFamily, ...]]]:
    """Return `(sql, families)` by model index for each pivot model no analysis covered."""

    models: dict[int, tuple[str, tuple[SchemaDynamicColumnFamily, ...]]] = {}
    for index, model_input in enumerate(model_inputs):
        families: tuple[SchemaDynamicColumnFamily, ...] = model_dynamic_families(model_input)
        if not families or model_input.model_file.file_path.stem in analyses:
            continue
        query_sql: str = cursor_intrinsics_analysis_sql(
            sql=model_input.query_sql,
            cursor_type=model_input.config.values.get("cursor_type"),
        )
        models[index] = (
            model_pivot_sql(query_sql=query_sql, placeholders=model_placeholders(model_input)),
            families,
        )
    return models
