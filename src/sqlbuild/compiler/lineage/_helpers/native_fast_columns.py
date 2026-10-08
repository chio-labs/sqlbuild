"""Fast column lineage built by the native engine, assembled exactly as Python assembles it."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompactLineageFacts,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompiledModel,
    CompiledProject,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage._helpers.columns import _build_schema_mapping
from sqlbuild.compiler.lineage._helpers.fast_columns import (
    _build_polyglot_fast_model_column_lineage,
)
from sqlbuild.compiler.lineage._helpers.native_deferrals import record_lineage_deferral
from sqlbuild.compiler.lineage.constants import (
    NATIVE_LINEAGE_BUILT,
    NATIVE_LINEAGE_DEFERRED,
    NATIVE_LINEAGE_STAR,
    NATIVE_LINEAGE_UNPARSED,
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

type _NativeColumn = tuple[str, str, str, list[tuple[str, str, str]]]
type _NativeOutcome = tuple[str, list[_NativeColumn], bool, str | None]


def build_native_fast_project_column_lineage(
    *,
    project: CompiledProject,
    dialect: str | None,
    model_names: frozenset[str] | None,
) -> ProjectColumnLineage | None:
    """Build `build_fast_project_column_lineage`'s graph with native star expansion and parsing."""

    if not project.settings.sql_analysis:
        return None
    models: tuple[CompiledModel, ...] = tuple(
        model for model in project.models if model_names is None or model.name in model_names
    )
    requests: list[tuple[bool, str, list[str]]] = []
    for model in models:
        request: tuple[bool, str, list[str]] | None = _native_request(model)
        if request is not None:
            requests.append(request)
    outcomes: list[_NativeOutcome] = (
        _native.build_fast_column_lineage(dialect, _schema_resources(project), requests)
        if requests
        else []
    )
    outcome_index: int = 0
    python_schema: dict[str, dict[str, str]] | None = None
    model_results: dict[str, ModelColumnLineage] = {}
    compact_models: dict[str, tuple[Sequence[CompiledLineageColumnFact], bool]] = {}
    model_order: list[str] = []
    for model in models:
        if model.fast_lineage_columns is not None:
            columns: Sequence[CompiledLineageColumnFact] = model.fast_lineage_columns
            if _needs_star_expansion(model):
                status, star_columns, _, _ = outcomes[outcome_index]
                outcome_index += 1
                if status != NATIVE_LINEAGE_STAR:
                    return None
                columns = (*columns, *(_column_fact(column) for column in star_columns))
            compact_models[model.name] = (columns, model.fast_lineage_has_star)
            model_order.append(model.name)
            continue
        status, built_columns, has_star, detail = outcomes[outcome_index]
        outcome_index += 1
        result: ModelColumnLineage | None = None
        if status == NATIVE_LINEAGE_BUILT:
            result = ModelColumnLineage(
                model_name=model.name,
                columns=tuple(_column_lineage(column) for column in built_columns),
                has_star=has_star,
            )
        elif status == NATIVE_LINEAGE_UNPARSED:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message="fast column lineage parse failed; falling back",
                sqlbuild_model=model.name,
                sqlbuild_error=detail,
            )
        elif status == NATIVE_LINEAGE_DEFERRED:
            record_lineage_deferral(kind=str(detail))
            if python_schema is None:
                python_schema = _build_schema_mapping(project)
            result = _build_polyglot_fast_model_column_lineage(
                model=model, schema=python_schema, dialect=dialect
            )
        if result is None:
            continue
        model_results[model.name] = result
        model_order.append(model.name)
    return ProjectColumnLineage.from_fast_facts(
        models=model_results,
        compact_models=compact_models,
        model_order=tuple(model_order),
    )


def _needs_star_expansion(model: CompiledModel) -> bool:
    return model.fast_lineage_has_star and not model.fast_lineage_star_resolved


def _native_request(model: CompiledModel) -> tuple[bool, str, list[str]] | None:
    columns: Sequence[CompiledLineageColumnFact] | None = model.fast_lineage_columns
    if columns is None:
        return (False, model.query_sql, [column.name for column in model.inferred_columns or ()])
    if not _needs_star_expansion(model):
        return None
    if isinstance(columns, CompactLineageFacts):
        return (True, model.query_sql, [columns.string_pool[row[0]] for row in columns.rows])
    return (True, model.query_sql, [column.output_column for column in columns])


def _schema_resources(project: CompiledProject) -> list[tuple[str, str, list[str]]]:
    resources: list[tuple[str, str, list[str]]] = []
    for model in project.models:
        columns: list[str] = [column.name for column in model.inferred_columns or ()]
        if model.schema_entry is not None:
            columns.extend(column.name for column in model.schema_entry.columns)
        resources.append((CompiledResourceType.MODEL.value, model.name, columns))
    for source in project.sources:
        resources.append(
            (
                CompiledResourceType.SOURCE.value,
                source.name,
                [column.name for column in source.source_entry.columns],
            )
        )
    for seed in project.seeds:
        resources.append(
            (
                CompiledResourceType.SEED.value,
                seed.name,
                [column.name for column in seed.schema_entry.columns],
            )
        )
    return resources


def _column_fact(column: _NativeColumn) -> CompiledLineageColumnFact:
    output_column, transform_kind, confidence, sources = column
    return CompiledLineageColumnFact(
        output_column=output_column,
        upstream_columns=tuple(
            CompiledLineageSourceFact(
                resource_type=resource_type,
                resource_name=resource_name,
                column_name=column_name,
            )
            for resource_type, resource_name, column_name in sources
        ),
        transform_kind=ColumnTransformKind(transform_kind),
        confidence=ColumnLineageConfidence(confidence),
    )


def _column_lineage(column: _NativeColumn) -> ColumnLineage:
    output_column, transform_kind, confidence, sources = column
    return ColumnLineage(
        output_column=output_column,
        transform_kind=ColumnTransformKind(transform_kind),
        expression_sql=None,
        upstream_columns=tuple(
            ColumnLineageSource(
                resource_type=resource_type,
                resource_name=resource_name,
                column_name=column_name,
            )
            for resource_type, resource_name, column_name in sources
        ),
        nullability=InferredNullability.UNKNOWN,
        confidence=ColumnLineageConfidence(confidence),
    )
