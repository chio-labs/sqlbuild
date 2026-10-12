"""Authoritative relation shapes shared by offline and warehouse validation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._infer_native_expression_source_shapes import (
    infer_native_expression_source_shapes,
)
from sqlbuild.compiler.compile._helpers.analysis.reference_names import table_function_analysis_name
from sqlbuild.compiler.compile.models import (
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import (
    CompiledModelView,
    CompiledProjectView,
    ModelInput,
)
from sqlbuild.compiler.planner.constants import (
    SNAPSHOT_DEFAULT_VALID_FROM_COLUMN,
    SNAPSHOT_DEFAULT_VALID_TO_COLUMN,
)
from sqlbuild.compiler.planner.types import ContractPolicy, MaterializationType
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import (
    CASE_SENSITIVE_BINDING_DIALECTS,
)
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from sqlbuild.spec.contracts.models import (
    SourceEntry,
)


def binding_relation_names(references: tuple[CompileSqlReference, ...]) -> frozenset[str]:
    return binding_relation_row_names(
        [(str(reference.ref_kind), reference.ref_name, None, None) for reference in references]
    )


def binding_relation_row_names(
    rows: list[tuple[str, str, str | None, int | None]],
) -> frozenset[str]:
    """The analysis names `(kind, name, package, count)` reference rows bind, UDFs excluded."""

    return frozenset(
        table_function_analysis_name(name) if kind == SqlReferenceKind.TABLE_FUNCTION else name
        for kind, name, _, _ in rows
        if kind != SqlReferenceKind.UDF
    )


def binding_required_names(model_input: ModelInput) -> frozenset[str] | None:
    if not model_input.sql_validation_enabled:
        return None
    return binding_relation_row_names(model_input.reference_rows)


def published_model_shape(
    *,
    sql: str,
    columns: dict[str, str],
    inputs: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
    config_values: dict[str, object],
) -> dict[str, str]:
    """Return a model relation's shape, including snapshot validity columns."""
    shape: dict[str, str] = inferred_binding_shape(
        sql=sql, columns=columns, inputs=inputs, profile=profile
    )
    if config_values.get("materialized") == MaterializationType.SNAPSHOT:
        for name in (
            config_values.get("valid_from_column") or SNAPSHOT_DEFAULT_VALID_FROM_COLUMN,
            config_values.get("valid_to_column") or SNAPSHOT_DEFAULT_VALID_TO_COLUMN,
        ):
            shape[str(name)] = "UNKNOWN"
    return shape


def binding_schema_for_model(
    *, model_input: ModelInput, complete_binding_schemas: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]] | None:
    required_names: frozenset[str] | None = binding_required_names(model_input)
    if required_names is None:
        return None
    return {name: complete_binding_schemas.get(name) or {} for name in required_names}


def inferred_binding_shape(
    *,
    sql: str,
    columns: dict[str, str],
    inputs: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> dict[str, str]:
    if (
        profile.quoted_identifiers_ignore_case
        or profile.sql_analysis_dialect not in CASE_SENSITIVE_BINDING_DIALECTS
    ):
        return columns
    catalog: Any = profile.binding_catalog or create_binding_catalog(
        dialect=profile.sql_analysis_dialect or "generic",
        quoted_ignore_case=False,
        known_functions=profile.semantic_known_functions,
        known_types=profile.semantic_known_types,
        relations=inputs,
    )
    return catalog.inferred_schema(
        sql=normalize_analysis_sql(sql=sql, dialect=profile.sql_analysis_dialect),
        columns=columns,
        inputs=inputs,
    )


def semantic_shapes(
    *,
    project: CompiledProjectView,
    profile: ExpressionInferenceProfile | None = None,
) -> dict[str, dict[str, str]]:
    """Return closed shapes; absence means open, never an empty physical table."""

    profile = profile or ExpressionInferenceProfile(
        sql_analysis_dialect=project.sql_analysis_dialect
    )
    profile = replace(profile, binding_catalog=project.binding_catalog)
    shapes: dict[str, dict[str, str]] = {}
    for seed in project.seeds:
        shapes[seed.name] = {
            column.name: column.type or "UNKNOWN" for column in seed.schema_entry.columns
        }
    for function in project.functions:
        if function.return_columns:
            shapes[table_function_analysis_name(function.name)] = {
                column.name: column.type for column in function.return_columns
            }
    expression_sources: list[tuple[str, str]] = []
    for source in project.sources:
        entry: SourceEntry = source.source_entry
        if entry.contract == ContractPolicy.ENFORCED:
            shapes[source.name] = {
                column.name: column.type or "UNKNOWN" for column in entry.columns
            }
        elif entry.expression:
            expression_sources.append((source.name, entry.expression))
    source_shapes: tuple[dict[str, str] | None, ...] = infer_native_expression_source_shapes(
        expressions=tuple(expression for _, expression in expression_sources), profile=profile
    )
    for (source_name, _), source_shape in zip(expression_sources, source_shapes, strict=True):
        if source_shape is not None:
            shapes[source_name] = source_shape
    pending: list[CompiledModelView] = list(project.models)
    while pending:
        remaining: list[CompiledModelView] = []
        for model in pending:
            declared: list[tuple[str, str | None]] | None = model.schema_column_rows
            inferred: list[tuple[str, str | None, str]] | None = model.inferred_rows
            rows: list[tuple[str, str, str | None, int | None]] = model.reference_rows
            relations: frozenset[str] = binding_relation_row_names(rows)
            if (
                model.config.values.get("contract") == ContractPolicy.ENFORCED
                and declared is not None
                and not model.has_dynamic_columns
            ):
                unchecked: frozenset[str] = model.unchecked_output_columns
                shapes[model.name] = {
                    name: "UNKNOWN" if name in unchecked else column_type or "UNKNOWN"
                    for name, column_type in declared
                }
            elif inferred and (
                not model.fast_lineage_has_star
                or (model.fast_lineage_star_resolved and rows and relations <= shapes.keys())
            ):
                shapes[model.name] = published_model_shape(
                    sql=model.query_sql,
                    profile=replace(profile, binding_catalog=project.binding_catalog),
                    columns={name: column_type or "UNKNOWN" for name, column_type, _ in inferred},
                    inputs={name: shapes.get(name, {}) for name in relations},
                    config_values=model.config.values,
                )
            else:
                remaining.append(model)
        if len(remaining) == len(pending):
            break
        pending = remaining
    return shapes
