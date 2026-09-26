"""Authoritative relation shapes shared by offline and warehouse validation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.columns import table_function_analysis_name
from sqlbuild.compiler.compile._helpers.analysis.compact import (
    NativeCompactAnalysis,
    analyze_columns_and_lineage_with_polyglot,
    analyze_queries_with_compact_polyglot_batch,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompileModelInput,
    CompileProjectInputs,
    CompileSqlReference,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import (
    CASE_SENSITIVE_BINDING_DIALECTS,
    NATIVE_DIALECT_ALIASES,
)
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from sqlbuild.spec.contracts.models import SourceEntry


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
    for source in project.sources:
        entry: SourceEntry = source.source_entry
        if entry.contract == ContractPolicy.ENFORCED:
            shapes[source.name] = {
                column.name: column.type or "UNKNOWN" for column in entry.columns
            }
        elif entry.expression:
            source_shape: dict[str, str] | None = get_expression_source_shape(
                expression=entry.expression, profile=profile
            )
            if source_shape is not None:
                shapes[source.name] = source_shape
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
                    model.references
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
                shapes[model.name] = inferred_binding_shape(
                    sql=model.query_sql,
                    profile=replace(profile, binding_catalog=project.binding_catalog),
                    columns={
                        column.name: column.type or "UNKNOWN" for column in model.inferred_columns
                    },
                    inputs={
                        name: shapes.get(name, {})
                        for name in binding_relation_names(model.references)
                    },
                )
            else:
                remaining.append(model)
        if len(remaining) == len(pending):
            break
        pending = remaining
    return shapes


def get_expression_source_shape(
    *, expression: str, profile: ExpressionInferenceProfile | None
) -> dict[str, str] | None:
    """Infer an expression source's closed output without declaring partial columns complete."""
    effective_profile: ExpressionInferenceProfile = profile or ExpressionInferenceProfile()
    effective_profile = replace(
        effective_profile,
        sql_analysis_dialect=NATIVE_DIALECT_ALIASES.get(
            effective_profile.sql_analysis_dialect or "generic",
            effective_profile.sql_analysis_dialect,
        ),
    )
    key: tuple[str, str | None, bool, tuple[tuple[str, str], ...]] = (
        expression,
        effective_profile.sql_analysis_dialect,
        effective_profile.quoted_identifiers_ignore_case,
        tuple(sorted(effective_profile.function_return_types.items())),
    )
    catalog: Any = effective_profile.binding_catalog
    if catalog is not None and key in catalog.expression_shapes:
        cached: dict[str, str] | None = catalog.expression_shapes[key]
        return None if cached is None else dict(cached)
    prepared: tuple[NativeCompactAnalysis, ...] = analyze_queries_with_compact_polyglot_batch(
        query_sqls=(expression,),
        references=((),),
        placeholders=(None,),
        column_nullability_by_table={},
        column_types_by_table={},
        inference_profile=effective_profile,
        recover_cte_facts=(True,),
        rich_type_inference=True,
    )
    analysis: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=expression,
        references=(),
        inference_profile=effective_profile,
        allow_compact_analysis=True,
        recover_cte_facts=True,
        precomputed=prepared[0],
    )
    shape: dict[str, str] | None = (
        None
        if not analysis.columns or analysis.has_star
        else inferred_binding_shape(
            sql=expression,
            profile=effective_profile,
            columns={column.name: column.type or "UNKNOWN" for column in analysis.columns},
            inputs={},
        )
    )
    if catalog is not None:
        catalog.expression_shapes[key] = shape
    return None if shape is None else dict(shape)
