"""Authoritative relation shapes shared by offline and warehouse validation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._infer_native_expression_source_shapes import (
    infer_native_expression_source_shapes,
)
from sqlbuild.compiler.compile._helpers.analysis.columns import table_function_analysis_name
from sqlbuild.compiler.compile.constants import NOT_NULL_AUDIT_NAME
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompileModelInput,
    CompileProjectInputs,
    CompileSqlReference,
)
from sqlbuild.compiler.lineage.types import InferredNullability
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
    SchemaAuditInstance,
    SchemaColumn,
    SourceColumnEntry,
    SourceEntry,
)


def binding_relation_names(references: tuple[CompileSqlReference, ...]) -> frozenset[str]:
    return frozenset(
        table_function_analysis_name(reference.ref_name)
        if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION
        else reference.ref_name
        for reference in references
        if reference.ref_kind != SqlReferenceKind.UDF
    )


def binding_required_names(model_input: CompileModelInput) -> frozenset[str] | None:
    if not model_input.sql_validation_enabled:
        return None
    return binding_relation_names(model_input.references)


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
    *, model_input: CompileModelInput, complete_binding_schemas: dict[str, dict[str, str]]
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


def build_declared_column_types(inputs: CompileProjectInputs) -> dict[str, dict[str, str]]:
    """Collect declared type hints independently of closed-schema authority."""
    facts: dict[str, dict[str, str]] = {}
    for model_input in inputs.model_inputs:
        if model_input.schema_entry is not None:
            facts[model_input.schema_entry.name] = {
                column.name: column.type or "UNKNOWN" for column in model_input.schema_entry.columns
            }
    for seed_input in inputs.seed_inputs:
        facts[seed_input.schema_entry.name] = {
            column.name: column.type or "UNKNOWN" for column in seed_input.schema_entry.columns
        }
    for source_input in inputs.source_inputs:
        facts[source_input.source_entry.name] = {
            column.name: column.type or "UNKNOWN" for column in source_input.source_entry.columns
        }
    for function_input in inputs.sql_function_inputs:
        if function_input.return_columns:
            facts[table_function_analysis_name(function_input.name)] = {
                column.name: column.type for column in function_input.return_columns
            }
    return facts


def build_column_nullability_by_table(
    inputs: CompileProjectInputs,
) -> dict[str, dict[str, InferredNullability]]:
    """Return what each model, seed, source and table function declares about column nulls."""

    facts: dict[str, dict[str, InferredNullability]] = {}
    for model_input in inputs.model_inputs:
        if model_input.schema_entry is None:
            continue
        facts[model_input.schema_entry.name] = _schema_column_nullability(
            model_input.schema_entry.columns
        )
    for seed_input in inputs.seed_inputs:
        facts[seed_input.schema_entry.name] = _schema_column_nullability(
            seed_input.schema_entry.columns
        )
    for source_input in inputs.source_inputs:
        facts[source_input.source_entry.name] = _source_column_nullability(
            source_input.source_entry.columns
        )
    for function_input in inputs.sql_function_inputs:
        if not function_input.return_columns:
            continue
        facts[table_function_analysis_name(function_input.name)] = {
            column.name: InferredNullability.UNKNOWN for column in function_input.return_columns
        }
    return facts


def _schema_column_nullability(
    columns: tuple[SchemaColumn, ...],
) -> dict[str, InferredNullability]:
    return {
        column.name: _declared_column_nullability(nullable=column.nullable, audits=column.audits)
        for column in columns
    }


def _source_column_nullability(
    columns: tuple[SourceColumnEntry, ...],
) -> dict[str, InferredNullability]:
    return {
        column.name: _declared_column_nullability(nullable=column.nullable, audits=column.audits)
        for column in columns
    }


def _declared_column_nullability(
    *,
    nullable: bool | None,
    audits: tuple[SchemaAuditInstance, ...],
) -> InferredNullability:
    if nullable is False:
        return InferredNullability.NON_NULL
    if any(audit.definition_name == NOT_NULL_AUDIT_NAME for audit in audits):
        return InferredNullability.NON_NULL
    return InferredNullability.UNKNOWN


def build_complete_binding_schemas(inputs: CompileProjectInputs) -> dict[str, dict[str, str]]:
    """Collect authoritative declared interfaces before SQL inference."""
    schemas: dict[str, dict[str, str]] = {}
    for model in inputs.model_inputs:
        if (
            model.config.values.get("contract") == ContractPolicy.ENFORCED
            and model.schema_entry is not None
            and model.schema_entry.columns
            and not model.schema_entry.dynamic_columns
        ):
            schemas[model.model_file.file_path.stem] = {
                column.name: column.type or "UNKNOWN" for column in model.schema_entry.columns
            }
    for source in inputs.source_inputs:
        if source.source_entry.contract == ContractPolicy.ENFORCED and source.source_entry.columns:
            schemas[source.source_entry.name] = {
                column.name: column.type or "UNKNOWN" for column in source.source_entry.columns
            }
    for seed in inputs.seed_inputs:
        if seed.schema_entry.columns:
            schemas[seed.schema_entry.name] = {
                column.name: column.type or "UNKNOWN" for column in seed.schema_entry.columns
            }
    for function in inputs.sql_function_inputs:
        if function.return_columns:
            schemas[table_function_analysis_name(function.name)] = {
                column.name: column.type for column in function.return_columns
            }
    return schemas


def semantic_shapes(
    *,
    project: CompiledProject,
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
    pending: list[CompiledModel] = list(project.models)
    while pending:
        remaining: list[CompiledModel] = []
        for model in pending:
            if (
                model.config.values.get("contract") == ContractPolicy.ENFORCED
                and model.schema_entry
                and not model.schema_entry.dynamic_columns
            ):
                shapes[model.name] = {
                    column.name: "UNKNOWN"
                    if column.name in model.unchecked_output_columns
                    else column.type or "UNKNOWN"
                    for column in model.schema_entry.columns
                }
            elif model.inferred_columns and (
                not model.fast_lineage_has_star
                or (
                    model.fast_lineage_star_resolved
                    and model.references
                    and all(
                        (
                            table_function_analysis_name(reference.ref_name)
                            if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION
                            else reference.ref_name
                        )
                        in shapes
                        for reference in model.references
                        if reference.ref_kind != SqlReferenceKind.UDF
                    )
                )
            ):
                shapes[model.name] = published_model_shape(
                    sql=model.query_sql,
                    profile=replace(profile, binding_catalog=project.binding_catalog),
                    columns={
                        column.name: column.type or "UNKNOWN" for column in model.inferred_columns
                    },
                    inputs={
                        name: shapes.get(name, {})
                        for name in binding_relation_names(model.references)
                    },
                    config_values=model.config.values,
                )
            else:
                remaining.append(model)
        if len(remaining) == len(pending):
            break
        pending = remaining
    return shapes


def referenced_model_names(
    *, model_input: CompileModelInput, available_names: frozenset[str] | None = None
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                reference.ref_name
                for reference in model_input.references
                if reference.ref_kind == SqlReferenceKind.REF
                and (available_names is None or reference.ref_name in available_names)
            }
        )
    )


def upstream_signatures(
    *, model_input: CompileModelInput, signatures: dict[str, str], available_names: frozenset[str]
) -> dict[str, str]:
    """Return the output signatures of the analyzed models this model references."""

    return {
        name: signatures[name]
        for name in referenced_model_names(model_input=model_input, available_names=available_names)
        if name in signatures
    }
