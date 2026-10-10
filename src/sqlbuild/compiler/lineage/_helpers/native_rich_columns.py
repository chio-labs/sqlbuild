"""Rich column lineage built by the native engine, assembled exactly as Python assembles it."""

from __future__ import annotations

import logging

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage._helpers.rich_columns import (
    _polyglot_dialect,
    assemble_rich_project_column_lineage,
)
from sqlbuild.compiler.lineage.constants import (
    NATIVE_LINEAGE_BUILT,
    NATIVE_RICH_LINEAGE_SKIPPED,
)
from sqlbuild.compiler.lineage.models import (
    ColumnLineage,
    ColumnLineageSource,
    ModelColumnLineage,
    ProjectColumnLineage,
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.lineage")

type _TypedColumns = list[tuple[str, str | None]]
type _NativeColumn = tuple[str, str, str, str, list[tuple[str, str, str]]]
type _NativeOutcome = tuple[str, list[_NativeColumn], bool, str | None]


def build_native_rich_project_column_lineage(
    *,
    project: CompiledProject,
    dialect: str | None,
    model_names: frozenset[str] | None,
) -> ProjectColumnLineage | None:
    """Build the rich project column lineage graph with native query analysis."""

    if not project.settings.sql_analysis:
        return None
    models: tuple[CompiledModel, ...] = tuple(
        model for model in project.models if model_names is None or model.name in model_names
    )
    outcomes: list[_NativeOutcome] = (
        _native.build_rich_column_lineage(
            (
                _polyglot_dialect(dialect).value,
                _schema_resources(project),
                [model.query_sql for model in models],
            )
        )
        if models
        else []
    )
    model_results: dict[str, ModelColumnLineage] = {}
    for model, (status, columns, has_star, detail) in zip(models, outcomes, strict=True):
        if status == NATIVE_LINEAGE_BUILT:
            model_results[model.name] = ModelColumnLineage(
                model_name=model.name,
                columns=tuple(_column_lineage(column) for column in columns),
                has_star=has_star,
            )
        elif status == NATIVE_RICH_LINEAGE_SKIPPED:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message="rich column lineage analysis failed; skipping model",
                sqlbuild_model=model.name,
                sqlbuild_error=detail,
            )
    return assemble_rich_project_column_lineage(model_results)


def _schema_resources(
    project: CompiledProject,
) -> list[tuple[str, str, _TypedColumns, _TypedColumns]]:
    resources: list[tuple[str, str, _TypedColumns, _TypedColumns]] = []
    for model in project.models:
        resources.append(
            (
                CompiledResourceType.MODEL.value,
                model.name,
                [(column.name, column.type) for column in model.inferred_columns or ()],
                [
                    (column.name, column.type)
                    for column in (
                        model.schema_entry.columns if model.schema_entry is not None else ()
                    )
                ],
            )
        )
    for source in project.sources:
        resources.append(
            (
                CompiledResourceType.SOURCE.value,
                source.name,
                [(column.name, column.type) for column in source.source_entry.columns],
                [],
            )
        )
    for seed in project.seeds:
        resources.append(
            (
                CompiledResourceType.SEED.value,
                seed.name,
                [(column.name, column.type) for column in seed.schema_entry.columns],
                [],
            )
        )
    return resources


def _column_lineage(column: _NativeColumn) -> ColumnLineage:
    output_column, transform_kind, confidence, nullability, sources = column
    return ColumnLineage(
        output_column=output_column,
        transform_kind=ColumnTransformKind(transform_kind),
        expression_sql=None,
        upstream_columns=tuple(
            ColumnLineageSource(
                resource_type=CompiledResourceType(resource_type),
                resource_name=resource_name,
                column_name=column_name,
            )
            for resource_type, resource_name, column_name in sources
        ),
        nullability=InferredNullability(nullability),
        confidence=ColumnLineageConfidence(confidence),
    )
