"""Authoritative relation shapes shared by offline and warehouse validation."""

from __future__ import annotations

from dataclasses import replace

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
    CompileProjectInputs,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import NATIVE_DIALECT_ALIASES
from sqlbuild.spec.contracts.models import SourceEntry


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
                    column.name: column.type or "UNKNOWN" for column in model.schema_entry.columns
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
                shapes[model.name] = {
                    column.name: column.type or "UNKNOWN" for column in model.inferred_columns
                }
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
    if not analysis.columns or analysis.has_star:
        return None
    return {column.name: column.type or "UNKNOWN" for column in analysis.columns}
