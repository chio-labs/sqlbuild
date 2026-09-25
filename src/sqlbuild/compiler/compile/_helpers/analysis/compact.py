"""Required SQL analysis-backed output inference, binding, and lineage facts."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.columns import (
    _analysis_reference_name,
    _analyze_columns_and_lineage_from_polyglot_ast,
    _infer_columns_with_polyglot,
    _infer_polyglot_nullability,
    _infer_polyglot_shallow_nullability,
    _lineage_resource_type,
    _polyglot_alias_nullability_from_select,
    _polyglot_expression_type,
    _qualified_reference_names,
    _replace_refs_with_stubs,
    substitute_placeholder_defaults,
)
from sqlbuild.compiler.compile._helpers.analysis.cte_facts import (
    _polyglot_cte_passthrough_facts,
    _polyglot_filtered_non_null_outputs,
)
from sqlbuild.compiler.compile.constants import (
    COMPACT_ANALYSIS_FACT_LENGTH,
    COMPACT_ANALYSIS_LEGACY_RESPONSE_LENGTH,
    COMPACT_ANALYSIS_RESPONSE_LENGTH,
    COMPACT_ANALYSIS_SOURCE_LENGTH,
    RESOLVED_SOURCE_CONFIDENCE,
    SQL_WILDCARD_TOKEN,
    UNKNOWN_SQL_TYPE_NAME,
)
from sqlbuild.compiler.compile.exceptions import CompactAnalysisInputError
from sqlbuild.compiler.compile.models import (
    CompactBatchExecutionOptions,
    CompactBatchPreparation,
    CompactLineageFacts,
    CompactProjectedFacts,
    CompactProjectionCaches,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    CteFactResolvers,
    InferredColumn,
    NativeCompactAnalysis,
    PolyglotAnalysisResult,
    ProjectedAnalysisRequest,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_BASE_TABLES as _POLYGLOT_ANALYSIS_BASE_TABLES,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_CAST_TYPE as _POLYGLOT_ANALYSIS_CAST_TYPE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_FUNCTION_NAME as _POLYGLOT_ANALYSIS_FUNCTION_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_IS_STAR as _POLYGLOT_ANALYSIS_IS_STAR,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NAME as _POLYGLOT_ANALYSIS_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NULLABILITY as _POLYGLOT_ANALYSIS_NULLABILITY,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL as _POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE as _POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_PROJECTIONS as _POLYGLOT_ANALYSIS_PROJECTIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_RELATIONS as _POLYGLOT_ANALYSIS_RELATIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE as _POLYGLOT_ANALYSIS_SHAPE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE_SELECT as _POLYGLOT_ANALYSIS_SHAPE_SELECT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION as _POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SOURCE_ALIAS as _POLYGLOT_ANALYSIS_SOURCE_ALIAS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE as _POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SOURCE_NAME as _POLYGLOT_ANALYSIS_SOURCE_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_STAR_PROJECTIONS as _POLYGLOT_ANALYSIS_STAR_PROJECTIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TABLE as _POLYGLOT_ANALYSIS_TABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION as _POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_CAST as _POLYGLOT_ANALYSIS_TRANSFORM_CAST,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT as _POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_DIRECT as _POLYGLOT_ANALYSIS_TRANSFORM_DIRECT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_FUNCTION as _POLYGLOT_ANALYSIS_TRANSFORM_FUNCTION,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_KIND as _POLYGLOT_ANALYSIS_TRANSFORM_KIND,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_STAR as _POLYGLOT_ANALYSIS_TRANSFORM_STAR,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TYPE_HINT as _POLYGLOT_ANALYSIS_TYPE_HINT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_UNSAFE_TRANSFORMS as _POLYGLOT_ANALYSIS_UNSAFE_TRANSFORMS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_UPSTREAM as _POLYGLOT_ANALYSIS_UPSTREAM,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_ALIAS as _POLYGLOT_PAYLOAD_ALIAS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_COLUMN as _POLYGLOT_PAYLOAD_COLUMN,
)
from sqlbuild.compiler.sql_analysis.exceptions import SqlAnalysisBoundaryError
from sqlbuild.compiler.sql_analysis.main._decode_schema_validation import decode_schema_validation
from sqlbuild.compiler.sql_analysis.main._prepare_schema_validation import prepare_schema_validation
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
    SqlBindingResult,
    SqlSchemaValidationRequest,
)
from sqlbuild.compiler.sql_analysis.types import NativeQueryAnalysisModule
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.compile")
_LARGE_COMPACT_PROJECT_MODELS: int = 10_000
_LARGE_COMPACT_SQL_BYTES: int = 48 * 1024 * 1024
_NATIVE_LEGACY_FALLBACK: str = "native project type recovery requires legacy fallback"


def infer_columns_with_sql_analysis(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
) -> tuple[InferredColumn, ...] | None:
    """Infer output columns from model query SQL using SQL analysis."""

    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()

    cleaned_sql: str = _replace_refs_with_stubs(
        query_sql=query_sql,
        dialect=profile.sql_analysis_dialect,
    )
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(
            query_sql=cleaned_sql, placeholders=placeholders
        )

    polyglot_columns: tuple[InferredColumn, ...] | None | bool = _infer_columns_with_polyglot(
        cleaned_sql=cleaned_sql,
        dialect=profile.sql_analysis_dialect,
        column_nullability_by_table=column_nullability_by_table or {},
        inference_profile=profile,
    )
    if isinstance(polyglot_columns, tuple):
        return polyglot_columns
    return None


def analyze_columns_and_lineage_with_polyglot(
    *,
    query_sql: str,
    references: tuple[CompileSqlReference, ...] = (),
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    column_types_by_table: dict[str, dict[str, str]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
    allow_compact_analysis: bool = False,
    binding_schema: dict[str, dict[str, str]] | None = None,
    recover_cte_facts: bool = False,
    precomputed: NativeCompactAnalysis | None = None,
) -> PolyglotAnalysisResult:
    """Infer columns and compact lineage facts from one Polyglot parse."""

    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    cleaned_sql: str = (
        precomputed.cleaned_sql
        if precomputed is not None
        else _cleaned_analysis_sql(
            query_sql=query_sql,
            placeholders=placeholders,
            dialect=profile.sql_analysis_dialect,
        )
    )
    if precomputed is not None and precomputed.projected:
        if precomputed.analysis is None and precomputed.compact_rows is None:
            return PolyglotAnalysisResult(
                analysis_succeeded=False,
                binding_diagnostics=precomputed.binding_diagnostics or (),
                binding_validated=binding_schema is not None,
            )
        return _projected_analysis_result(
            request=ProjectedAnalysisRequest(
                analysis=precomputed.analysis,
                compact_rows=precomputed.compact_rows,
                compact_fact_rows=precomputed.compact_fact_rows,
                string_pool=precomputed.string_pool,
                caches=CompactProjectionCaches(
                    columns=precomputed.compact_column_cache,
                    facts=precomputed.compact_fact_cache,
                    decoded_facts=precomputed.compact_decoded_fact_cache,
                ),
                template_index=precomputed.compact_template_index,
                resource_name_indexes=precomputed.resource_name_indexes,
                binding_diagnostics=(
                    precomputed.binding_diagnostics
                    if precomputed.binding_diagnostics is not None
                    else _validate_complete_binding_schema(
                        cleaned_sql=cleaned_sql,
                        dialect=profile.sql_analysis_dialect,
                        binding_schema=binding_schema,
                    )
                ),
                binding_validated=binding_schema is not None,
            )
        )
    polyglot_module: Any = import_polyglot_sql()
    compact_result: (
        tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool] | None
    ) = _analyze_columns_and_lineage_with_compact_polyglot(
        polyglot_module=polyglot_module,
        cleaned_sql=cleaned_sql,
        dialect=profile.sql_analysis_dialect,
        references=references,
        column_nullability_by_table=column_nullability_by_table or {},
        column_types_by_table=column_types_by_table or {},
        inference_profile=profile,
        allow_compact_analysis=(
            allow_compact_analysis
            and not (
                precomputed is not None
                and not precomputed.projected
                and precomputed.analysis is None
            )
        ),
        recover_cte_facts=recover_cte_facts,
        analysis=precomputed.analysis if precomputed is not None else None,
    )
    if compact_result is not None:
        return PolyglotAnalysisResult(
            analysis_succeeded=True,
            columns=compact_result[0],
            lineage_columns=compact_result[1],
            has_star=compact_result[2],
            binding_diagnostics=(
                precomputed.binding_diagnostics
                if precomputed is not None and precomputed.binding_diagnostics is not None
                else _validate_complete_binding_schema(
                    cleaned_sql=cleaned_sql,
                    dialect=profile.sql_analysis_dialect,
                    binding_schema=binding_schema,
                )
            ),
            binding_validated=binding_schema is not None,
        )
    try:
        parsed: Any = polyglot_module.parse_one(
            cleaned_sql,
            dialect=profile.sql_analysis_dialect or "generic",
        )
    except polyglot_module.PolyglotError as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="column and lineage analysis parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return PolyglotAnalysisResult(analysis_succeeded=False)
    columns, legacy_lineage_columns, has_star = _analyze_columns_and_lineage_from_polyglot_ast(
        parsed=parsed,
        references=references,
        column_nullability_by_table=column_nullability_by_table or {},
        column_types_by_table=column_types_by_table or {},
        inference_profile=profile,
        recover_cte_facts=recover_cte_facts,
    )
    lineage_columns: Sequence[CompiledLineageColumnFact] = legacy_lineage_columns
    if precomputed is not None and precomputed.compact_rows is not None:
        lineage_columns = _compact_projected_analysis_result(
            request=ProjectedAnalysisRequest(
                analysis=None,
                compact_rows=precomputed.compact_rows,
                compact_fact_rows=precomputed.compact_fact_rows,
                string_pool=precomputed.string_pool,
                caches=CompactProjectionCaches(
                    columns=precomputed.compact_column_cache,
                    facts=precomputed.compact_fact_cache,
                    decoded_facts=precomputed.compact_decoded_fact_cache,
                ),
                template_index=precomputed.compact_template_index,
                resource_name_indexes=precomputed.resource_name_indexes,
                binding_diagnostics=(),
                binding_validated=False,
            )
        ).lineage_columns
    return PolyglotAnalysisResult(
        analysis_succeeded=True,
        columns=columns,
        lineage_columns=lineage_columns,
        has_star=has_star,
        binding_diagnostics=(
            precomputed.binding_diagnostics
            if precomputed is not None and precomputed.binding_diagnostics is not None
            else _validate_complete_binding_schema(
                cleaned_sql=cleaned_sql,
                dialect=profile.sql_analysis_dialect,
                binding_schema=binding_schema,
            )
        ),
        binding_validated=binding_schema is not None,
    )


def analyze_queries_with_compact_polyglot_batch(
    *,
    query_sqls: tuple[str, ...],
    references: tuple[tuple[CompileSqlReference, ...], ...],
    placeholders: tuple[dict[str, str] | None, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    recover_cte_facts: tuple[bool, ...],
    rich_type_inference: bool = True,
    cached_batch: tuple[CompactBatchPreparation, object] | None = None,
    execution: CompactBatchExecutionOptions | None = None,
) -> tuple[NativeCompactAnalysis, ...]:
    """Analyze rendered SQL in one bounded native call, preserving input order."""

    options: CompactBatchExecutionOptions = execution or CompactBatchExecutionOptions()
    binding_schemas: tuple[dict[str, dict[str, str]] | None, ...] | None = options.binding_schemas

    if not (len(query_sqls) == len(references) == len(placeholders) == len(recover_cte_facts)):
        raise CompactAnalysisInputError(
            "compact query-analysis batch inputs must have equal lengths"
        )
    if binding_schemas is not None and len(binding_schemas) != len(query_sqls):
        raise CompactAnalysisInputError("binding schemas must match the query batch length")
    if cached_batch is not None:
        preparation: CompactBatchPreparation = cached_batch[0]
    else:
        with record_compile_timing("analysis_preparation_ms"):
            preparation = _prepare_compact_analysis_batch(
                query_sqls=query_sqls,
                references=references,
                placeholders=placeholders,
                column_nullability_by_table=column_nullability_by_table,
                column_types_by_table=column_types_by_table,
                inference_profile=inference_profile,
                recover_cte_facts=recover_cte_facts,
                rich_type_inference=rich_type_inference,
                binding_schemas=binding_schemas,
            )
    if len(preparation.cleaned_sql) != len(query_sqls):
        raise CompactAnalysisInputError(
            "cached compact query-analysis preparation has an invalid length"
        )
    if cached_batch is not None:
        response_payload: object = cached_batch[1]
    else:
        with record_compile_timing("analysis_native_ms"):
            response_payload = _run_compact_analysis_batch(preparation=preparation)
    with record_compile_timing("analysis_projection_ms"):
        projected: tuple[NativeCompactAnalysis, ...] = _project_compact_analysis_batch(
            preparation=preparation,
            response_payload=response_payload,
        )
        if cached_batch is None:
            projected = _attach_compiled_bindings(
                preparation=preparation,
                response=response_payload,
                analyses=projected,
            )
    if cached_batch is None and options.on_response is not None:
        options.on_response(preparation=preparation, response=response_payload)
    return projected


def _prepare_compact_analysis_batch(
    *,
    query_sqls: tuple[str, ...],
    references: tuple[tuple[CompileSqlReference, ...], ...],
    placeholders: tuple[dict[str, str] | None, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    recover_cte_facts: tuple[bool, ...],
    rich_type_inference: bool,
    binding_schemas: tuple[dict[str, dict[str, str]] | None, ...] | None = None,
) -> CompactBatchPreparation:
    dialect: str | None = inference_profile.sql_analysis_dialect
    prepared: list[str] = []
    queries: list[dict[str, object]] = []
    query_indexes: dict[tuple[str, str, bytes | None, bytes | None], int] = {}
    templates: list[dict[str, object]] = []
    template_indexes: dict[
        tuple[
            int,
            tuple[tuple[str, str], ...],
            tuple[tuple[str, str], ...],
            tuple[str, ...],
            bool,
            bool,
        ],
        int,
    ] = {}
    projections: list[dict[str, object]] = []
    function_return_types: dict[str, str] = dict(inference_profile.function_return_types)
    for (
        query_sql,
        query_references,
        query_placeholders,
        query_recover_cte_facts,
        binding_schema,
    ) in zip(
        query_sqls,
        references,
        placeholders,
        recover_cte_facts,
        binding_schemas if binding_schemas is not None else (None,) * len(query_sqls),
        strict=True,
    ):
        cleaned_sql: str = _cleaned_analysis_sql(
            query_sql=query_sql,
            placeholders=query_placeholders,
            dialect=dialect,
        )
        lineage_references: dict[str, tuple[CompiledResourceType, str]] = _lineage_reference_map(
            query_references
        )
        qualified_reference_names: frozenset[str] = (
            _qualified_reference_names(
                query_sql=cleaned_sql,
                reference_names=lineage_references.keys(),
            )
            if binding_schema is None
            else frozenset()
        )
        canonical_stubs: dict[str, str] = {
            name: (
                name
                if binding_schema is not None or name in qualified_reference_names
                else f"__sqlbuild_project_input_{index}"
            )
            for index, name in enumerate(lineage_references)
        }
        analysis_sql: str = (
            cleaned_sql
            if binding_schema is not None
            else _cleaned_analysis_sql(
                query_sql=query_sql,
                placeholders=query_placeholders,
                dialect=dialect,
                relation_stubs=canonical_stubs,
            )
        )
        query: dict[str, object] = {
            "sql": analysis_sql,
            "dialect": dialect or "generic",
        }
        schema: dict[str, object] | None = _compact_analysis_schema(
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            table_names=frozenset(
                _analysis_reference_name(reference) for reference in query_references
            ),
            table_name_aliases=canonical_stubs,
        )
        if schema is not None:
            query["schema"] = schema
        binding_payload: dict[str, object] | None = None
        if binding_schema is not None:
            binding_payload = prepare_schema_validation(
                request=SqlSchemaValidationRequest(
                    sql=cleaned_sql,
                    dialect=dialect,
                    schema=binding_schema,
                )
            )
            query["binding_schema"] = binding_payload["schema"]
        query_key: tuple[str, str, bytes | None, bytes | None] = (
            analysis_sql,
            dialect or "generic",
            (orjson.dumps(schema, option=orjson.OPT_SORT_KEYS) if schema is not None else None),
            (
                orjson.dumps(binding_payload["schema"], option=orjson.OPT_SORT_KEYS)
                if binding_payload is not None
                else None
            ),
        )
        query_index: int | None = query_indexes.get(query_key)
        if query_index is None:
            query_index = len(queries)
            query_indexes[query_key] = query_index
            queries.append(query)
        declared_column_order: tuple[str, ...] = (
            tuple(
                column_nullability_by_table.get(_analysis_reference_name(query_references[0]), {})
            )
            if len(query_references) == 1
            else ()
        )
        reference_types: tuple[tuple[str, str], ...] = tuple(
            (canonical_stubs[name], resource_type.value)
            for name, (resource_type, _) in lineage_references.items()
        )
        template_key: tuple[
            int,
            tuple[tuple[str, str], ...],
            tuple[tuple[str, str], ...],
            tuple[str, ...],
            bool,
            bool,
        ] = (
            query_index,
            reference_types,
            tuple(function_return_types.items()),
            declared_column_order,
            query_recover_cte_facts,
            rich_type_inference,
        )
        template_index: int | None = template_indexes.get(template_key)
        if template_index is None:
            template_index = len(templates)
            template_indexes[template_key] = template_index
            templates.append(
                {
                    "queryIndex": query_index,
                    "references": {
                        name: {
                            "resourceType": resource_type,
                            "resourceName": name,
                        }
                        for name, resource_type in reference_types
                    },
                    "functionReturnTypes": function_return_types,
                    "declaredColumnOrder": list(declared_column_order),
                    "recoverCteFacts": query_recover_cte_facts,
                    "richTypeInference": rich_type_inference,
                }
            )
        projections.append(
            {
                "templateIndex": template_index,
                "resourceNames": {
                    canonical_stubs[name]: resource_name
                    for name, (_, resource_name) in lineage_references.items()
                },
            }
        )
        prepared.append(cleaned_sql)
    return CompactBatchPreparation(
        cleaned_sql=tuple(prepared),
        queries=tuple(queries),
        templates=tuple(templates),
        projections=tuple(projections),
    )


def _run_compact_analysis_batch(*, preparation: CompactBatchPreparation) -> object:
    """Bound resident analysis heaps before the isolated custom-rule host starts."""

    large_project: bool = (
        len(preparation.projections) >= _LARGE_COMPACT_PROJECT_MODELS
        and sum(len(sql.encode("utf-8")) for sql in preparation.cleaned_sql)
        >= _LARGE_COMPACT_SQL_BYTES
    )
    workers: int = 1 if large_project else 4
    return orjson.loads(
        cast(NativeQueryAnalysisModule, _native).analyze_project_queries_compact_json(
            orjson.dumps(
                {
                    "queries": preparation.queries,
                    "templates": preparation.templates,
                    "projections": preparation.projections,
                    "workers": workers,
                },
                option=orjson.OPT_SORT_KEYS,
            ).decode()
        )
    )


def _attach_compiled_bindings(
    *,
    preparation: CompactBatchPreparation,
    response: object,
    analyses: tuple[NativeCompactAnalysis, ...],
) -> tuple[NativeCompactAnalysis, ...]:
    if not isinstance(response, dict):
        return analyses
    validations: object = cast(dict[str, object], response).get("validations")
    if validations is None:
        return analyses
    if not isinstance(validations, list) or len(validations) != len(preparation.queries):
        raise SqlAnalysisBoundaryError("native compilation returned an invalid binding batch")
    results: list[NativeCompactAnalysis] = []
    for analysis, projection in zip(analyses, preparation.projections, strict=True):
        template_index: int = cast(int, projection["templateIndex"])
        query_index: int = cast(int, preparation.templates[template_index]["queryIndex"])
        validation: object = validations[query_index]
        if validation is None:
            results.append(analysis)
            continue
        binding: SqlBindingResult = decode_schema_validation(
            sql=analysis.cleaned_sql,
            dialect=cast(str, preparation.queries[query_index]["dialect"]),
            response=validation,
        )
        results.append(replace(analysis, binding_diagnostics=binding.diagnostics))
    return tuple(results)


def _project_compact_analysis_batch(
    *, preparation: CompactBatchPreparation, response_payload: object
) -> tuple[NativeCompactAnalysis, ...]:
    if not isinstance(response_payload, dict):
        raise SqlAnalysisBoundaryError(
            "native compact query analysis returned an invalid batch response"
        )
    response_mapping: dict[str, object] = cast(dict[str, object], response_payload)
    raw_strings: object = response_mapping.get("strings")
    raw_facts: object = response_mapping.get("facts")
    templates: object = response_mapping.get("templates")
    responses: object = response_mapping.get("analyses")
    if (
        not isinstance(raw_strings, list)
        or not all(isinstance(value, str) for value in raw_strings)
        or not isinstance(raw_facts, list)
        or not isinstance(templates, list)
        or not isinstance(responses, list)
        or len(responses) != len(preparation.cleaned_sql)
    ):
        raise SqlAnalysisBoundaryError(
            "native compact query analysis returned an invalid batch response"
        )
    string_pool: tuple[str, ...] = tuple(cast(list[str], raw_strings))
    column_cache: dict[tuple[int, int | None, int], InferredColumn] = {}
    fact_cache: dict[int, CompactProjectedFacts] = {}
    decoded_fact_cache: dict[
        int,
        tuple[InferredColumn, tuple[int, int, int, tuple[tuple[int, int, int], ...]]],
    ] = {}
    results: list[NativeCompactAnalysis] = []
    for cleaned_sql, response in zip(preparation.cleaned_sql, responses, strict=True):
        if (
            isinstance(response, list)
            and len(response) == COMPACT_ANALYSIS_RESPONSE_LENGTH
            and isinstance(response[0], int)
            and not isinstance(response[0], bool)
            and isinstance(response[1], list)
        ):
            template_index: int = response[0]
            if template_index < 0:
                raise SqlAnalysisBoundaryError(
                    "native compact query analysis returned an invalid template index"
                )
            try:
                template: object = templates[template_index]
            except IndexError as error:
                raise SqlAnalysisBoundaryError(
                    "native compact query analysis returned an invalid template index"
                ) from error
            if isinstance(template, str):
                log_debug_event(
                    logger=_DEBUG_LOGGER,
                    message="native compact query analysis failed",
                    sqlbuild_error=template,
                )
                results.append(
                    NativeCompactAnalysis(
                        cleaned_sql=cleaned_sql,
                        analysis=None,
                        projected=template != _NATIVE_LEGACY_FALLBACK,
                    )
                )
                continue
            legacy_type_recovery: bool = (
                isinstance(template, list)
                and len(template) == COMPACT_ANALYSIS_LEGACY_RESPONSE_LENGTH
                and template[2] == _NATIVE_LEGACY_FALLBACK
            )
            if not (
                isinstance(template, list)
                and (len(template) == COMPACT_ANALYSIS_RESPONSE_LENGTH or legacy_type_recovery)
                and isinstance(template[0], list)
                and isinstance(template[1], bool)
            ):
                raise SqlAnalysisBoundaryError(
                    "native compact query analysis returned an invalid template"
                )
            resource_name_indexes: dict[int, int] = {}
            for raw_mapping in response[1]:
                if not (
                    isinstance(raw_mapping, list)
                    and len(raw_mapping) == COMPACT_ANALYSIS_RESPONSE_LENGTH
                    and all(
                        isinstance(value, int) and not isinstance(value, bool)
                        for value in raw_mapping
                    )
                ):
                    raise SqlAnalysisBoundaryError(
                        "native compact query analysis returned an invalid resource mapping"
                    )
                canonical_index, resource_index = cast(tuple[int, int], tuple(raw_mapping))
                try:
                    _ = string_pool[canonical_index]
                    _ = string_pool[resource_index]
                except IndexError as error:
                    raise SqlAnalysisBoundaryError(
                        "native compact query analysis returned an out-of-range resource index"
                    ) from error
                resource_name_indexes[canonical_index] = resource_index
            results.append(
                NativeCompactAnalysis(
                    cleaned_sql=cleaned_sql,
                    analysis=None if legacy_type_recovery else {"hasStar": template[1]},
                    projected=not legacy_type_recovery,
                    compact_rows=cast(list[object], template[0]),
                    compact_fact_rows=cast(list[object], raw_facts),
                    string_pool=string_pool,
                    compact_column_cache=column_cache,
                    compact_template_index=template_index,
                    compact_fact_cache=fact_cache,
                    compact_decoded_fact_cache=decoded_fact_cache,
                    resource_name_indexes=resource_name_indexes,
                )
            )
            continue
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="native compact query analysis failed",
            sqlbuild_error=str(response or "invalid native response"),
        )
        results.append(
            NativeCompactAnalysis(cleaned_sql=cleaned_sql, analysis=None, projected=True)
        )
    return tuple(results)


def _projected_analysis_result(*, request: ProjectedAnalysisRequest) -> PolyglotAnalysisResult:
    analysis: dict[str, Any] | None = request.analysis
    if request.compact_rows is not None:
        return _compact_projected_analysis_result(request=request)
    if analysis is None:
        raise SqlAnalysisBoundaryError("native project query analysis omitted facts")
    raw_columns: object = analysis.get("columns")
    raw_lineage: object = analysis.get("lineageColumns")
    if not isinstance(raw_columns, list) or not isinstance(raw_lineage, list):
        raise SqlAnalysisBoundaryError("native project query analysis returned invalid facts")
    columns: list[InferredColumn] = []
    for raw_column in raw_columns:
        if not isinstance(raw_column, dict):
            raise SqlAnalysisBoundaryError("native project query analysis returned invalid columns")
        name: object = raw_column.get("name")
        if not isinstance(name, str):
            raise SqlAnalysisBoundaryError("native project query analysis omitted a column name")
        data_type: object = raw_column.get("type")
        columns.append(
            InferredColumn(
                name=name,
                type=data_type if isinstance(data_type, str) else None,
                nullability=InferredNullability(str(raw_column.get("nullability") or "unknown")),
            )
        )
    lineage_columns: list[CompiledLineageColumnFact] = []
    for raw_column in raw_lineage:
        if not isinstance(raw_column, dict):
            raise SqlAnalysisBoundaryError("native project query analysis returned invalid lineage")
        output_column: object = raw_column.get("outputColumn")
        raw_upstream: object = raw_column.get("upstreamColumns")
        if not isinstance(output_column, str) or not isinstance(raw_upstream, list):
            raise SqlAnalysisBoundaryError("native project query analysis omitted lineage fields")
        upstream: list[CompiledLineageSourceFact] = []
        for raw_source in raw_upstream:
            if not isinstance(raw_source, dict):
                raise SqlAnalysisBoundaryError(
                    "native project query analysis returned invalid upstream lineage"
                )
            upstream.append(
                CompiledLineageSourceFact(
                    resource_type=str(raw_source.get("resourceType") or ""),
                    resource_name=str(raw_source.get("resourceName") or ""),
                    column_name=str(raw_source.get("columnName") or ""),
                )
            )
        lineage_columns.append(
            CompiledLineageColumnFact(
                output_column=output_column,
                upstream_columns=tuple(upstream),
                transform_kind=ColumnTransformKind(
                    str(raw_column.get("transformKind") or "unknown")
                ),
                confidence=ColumnLineageConfidence(str(raw_column.get("confidence") or "unknown")),
            )
        )
    return PolyglotAnalysisResult(
        analysis_succeeded=True,
        columns=tuple(columns),
        lineage_columns=tuple(lineage_columns),
        has_star=bool(analysis.get("hasStar")),
        binding_diagnostics=request.binding_diagnostics,
        binding_validated=request.binding_validated,
    )


def _compact_projected_analysis_result(
    *, request: ProjectedAnalysisRequest
) -> PolyglotAnalysisResult:
    rows: list[object] = request.compact_rows or []
    fact_rows: list[object] = request.compact_fact_rows or []
    string_pool: tuple[str, ...] = request.string_pool
    cached_facts: CompactProjectedFacts | None = request.caches.fact(request.template_index)
    if cached_facts is not None:
        return PolyglotAnalysisResult(
            analysis_succeeded=True,
            columns=cached_facts.columns,
            lineage_columns=CompactLineageFacts(
                string_pool=string_pool,
                rows=cached_facts.lineage_rows,
                resource_name_indexes=request.resource_name_indexes,
            ),
            has_star=bool(request.analysis and request.analysis.get("hasStar")),
            binding_diagnostics=request.binding_diagnostics,
            binding_validated=request.binding_validated,
        )
    nullability_by_code: tuple[InferredNullability, ...] = (
        InferredNullability.UNKNOWN,
        InferredNullability.NON_NULL,
        InferredNullability.NULLABLE,
    )
    transform_by_code: tuple[ColumnTransformKind, ...] = (
        ColumnTransformKind.DIRECT,
        ColumnTransformKind.CAST,
        ColumnTransformKind.EXPRESSION,
        ColumnTransformKind.AGGREGATION,
        ColumnTransformKind.STAR,
        ColumnTransformKind.CONSTANT,
    )
    confidence_by_code: tuple[ColumnLineageConfidence, ...] = (
        ColumnLineageConfidence.UNKNOWN,
        ColumnLineageConfidence.HIGH,
        ColumnLineageConfidence.MEDIUM,
    )

    def pooled_string(value: object) -> str:
        if not isinstance(value, int) or isinstance(value, bool):
            raise SqlAnalysisBoundaryError("native compact analysis returned an invalid index")
        try:
            return string_pool[value]
        except IndexError as error:
            raise SqlAnalysisBoundaryError(
                "native compact analysis returned an out-of-range index"
            ) from error

    columns: list[InferredColumn] = []
    compact_lineage_rows: list[tuple[int, int, int, tuple[tuple[int, int, int], ...]]] = []
    for raw_fact_index in rows:
        if (
            not isinstance(raw_fact_index, int)
            or isinstance(raw_fact_index, bool)
            or raw_fact_index < 0
        ):
            raise SqlAnalysisBoundaryError("native compact analysis returned an invalid fact index")
        decoded_fact: (
            tuple[
                InferredColumn,
                tuple[int, int, int, tuple[tuple[int, int, int], ...]],
            ]
            | None
        ) = request.caches.decoded_fact(raw_fact_index)
        if decoded_fact is not None:
            column, lineage_row = decoded_fact
            columns.append(column)
            compact_lineage_rows.append(lineage_row)
            continue
        try:
            raw_row: object = fact_rows[raw_fact_index]
        except IndexError as error:
            raise SqlAnalysisBoundaryError(
                "native compact analysis returned an out-of-range fact index"
            ) from error
        if not isinstance(raw_row, list) or len(raw_row) != COMPACT_ANALYSIS_FACT_LENGTH:
            raise SqlAnalysisBoundaryError("native compact analysis returned an invalid column")
        name_index, type_index, nullability_code, transform_code, confidence_code, raw_upstream = (
            raw_row
        )
        if (
            not isinstance(nullability_code, int)
            or isinstance(nullability_code, bool)
            or not isinstance(transform_code, int)
            or isinstance(transform_code, bool)
            or not isinstance(confidence_code, int)
            or isinstance(confidence_code, bool)
            or not isinstance(raw_upstream, list)
        ):
            raise SqlAnalysisBoundaryError("native compact analysis returned invalid column facts")
        try:
            nullability: InferredNullability = nullability_by_code[nullability_code]
            _ = transform_by_code[transform_code]
            _ = confidence_by_code[confidence_code]
        except IndexError as error:
            raise SqlAnalysisBoundaryError(
                "native compact analysis returned an invalid fact code"
            ) from error
        if not isinstance(name_index, int) or isinstance(name_index, bool):
            raise SqlAnalysisBoundaryError("native compact analysis returned an invalid name index")
        if type_index is not None and (
            not isinstance(type_index, int) or isinstance(type_index, bool)
        ):
            raise SqlAnalysisBoundaryError("native compact analysis returned an invalid type index")
        column_key: tuple[int, int | None, int] = (name_index, type_index, nullability_code)
        column: InferredColumn | None = request.caches.column(column_key)
        if column is None:
            column = InferredColumn(
                name=pooled_string(name_index),
                type=pooled_string(type_index) if type_index is not None else None,
                nullability=nullability,
            )
            request.caches.remember_column(key=column_key, column=column)
        columns.append(column)
        upstream: list[tuple[int, int, int]] = []
        for raw_source in raw_upstream:
            if (
                not isinstance(raw_source, list)
                or len(raw_source) != COMPACT_ANALYSIS_SOURCE_LENGTH
            ):
                raise SqlAnalysisBoundaryError(
                    "native compact analysis returned invalid upstream lineage"
                )
            if not all(
                isinstance(value, int) and not isinstance(value, bool) for value in raw_source
            ):
                raise SqlAnalysisBoundaryError(
                    "native compact analysis returned invalid upstream indexes"
                )
            source_key: tuple[int, int, int] = cast(tuple[int, int, int], tuple(raw_source))
            _ = pooled_string(source_key[0])
            _ = pooled_string(source_key[1])
            _ = pooled_string(source_key[2])
            upstream.append(source_key)
        lineage_row: tuple[int, int, int, tuple[tuple[int, int, int], ...]] = (
            name_index,
            transform_code,
            confidence_code,
            tuple(upstream),
        )
        compact_lineage_rows.append(lineage_row)
        request.caches.remember_decoded_fact(fact_index=raw_fact_index, fact=(column, lineage_row))
    compact_facts: CompactProjectedFacts = CompactProjectedFacts(
        columns=tuple(columns),
        lineage_rows=tuple(compact_lineage_rows),
    )
    request.caches.remember_fact(template_index=request.template_index, fact=compact_facts)
    return PolyglotAnalysisResult(
        analysis_succeeded=True,
        columns=compact_facts.columns,
        lineage_columns=CompactLineageFacts(
            string_pool=string_pool,
            rows=compact_facts.lineage_rows,
            resource_name_indexes=request.resource_name_indexes,
        ),
        has_star=bool(request.analysis and request.analysis.get("hasStar")),
        binding_diagnostics=request.binding_diagnostics,
        binding_validated=request.binding_validated,
    )


def _cleaned_analysis_sql(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None,
    dialect: str | None,
    relation_stubs: dict[str, str] | None = None,
) -> str:
    cleaned_sql: str = _replace_refs_with_stubs(
        query_sql=query_sql,
        dialect=dialect,
        relation_stubs=relation_stubs,
    )
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(
            query_sql=cleaned_sql,
            placeholders=placeholders,
        )
    return cleaned_sql


def get_complete_schema_binding_request(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None,
    dialect: str | None,
    binding_schema: dict[str, dict[str, str]],
) -> SqlSchemaValidationRequest:
    """Build one stable native schema-validation request."""

    cleaned_sql: str = _replace_refs_with_stubs(query_sql=query_sql, dialect=dialect)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(
            query_sql=cleaned_sql,
            placeholders=placeholders,
        )
    return SqlSchemaValidationRequest(
        sql=cleaned_sql,
        dialect=dialect,
        schema=binding_schema,
    )


def _validate_complete_binding_schema(
    *,
    cleaned_sql: str,
    dialect: str | None,
    binding_schema: dict[str, dict[str, str]] | None,
) -> tuple[SqlBindingDiagnostic, ...]:
    if binding_schema is None:
        return ()
    return get_schema_validations(
        requests=(
            SqlSchemaValidationRequest(
                sql=cleaned_sql,
                dialect=dialect,
                schema=binding_schema,
            ),
        )
    )[0].diagnostics


def _analyze_columns_and_lineage_with_compact_polyglot(
    *,
    polyglot_module: Any,
    cleaned_sql: str,
    dialect: str | None,
    references: tuple[CompileSqlReference, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    recover_cte_facts: bool,
    analysis: dict[str, Any] | None = None,
) -> tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool] | None:
    if not allow_compact_analysis:
        return None
    try:
        options: dict[str, object] = {"dialect": dialect or "generic"}
        schema: dict[str, object] | None = _compact_analysis_schema(
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            table_names=frozenset(_analysis_reference_name(reference) for reference in references),
        )
        if schema is not None:
            options["schema"] = schema
        if analysis is None:
            analysis = polyglot_module.analyze_query(cleaned_sql, options)
    except polyglot_module.PolyglotError as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="compact query analysis failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    if not isinstance(analysis, dict):
        return None
    projections: object = analysis.get(_POLYGLOT_ANALYSIS_PROJECTIONS)
    if not isinstance(projections, list):
        return None
    if not _compact_analysis_is_eligible(analysis=analysis, projections=projections):
        return None
    reference_map: dict[str, tuple[CompiledResourceType, str]] = _lineage_reference_map(references)
    relation_alias_by_name: dict[str, str | None] = _compact_relation_alias_by_name(analysis)
    cte_passthrough_types, cte_passthrough_nullability, direct_cte_outputs, parsed = (
        _polyglot_cte_passthrough_facts(
            polyglot_module=polyglot_module,
            cleaned_sql=cleaned_sql,
            dialect=dialect,
            column_types_by_table=column_types_by_table,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
            analysis=analysis,
            resolvers=CteFactResolvers(
                expression_type=_polyglot_expression_type,
                nullability=_infer_polyglot_nullability,
                shallow_nullability=_infer_polyglot_shallow_nullability,
                alias_nullability=_polyglot_alias_nullability_from_select,
            ),
        )
        if recover_cte_facts
        else ({}, {}, frozenset(), None)
    )
    filtered_non_null_outputs: frozenset[str] = _polyglot_filtered_non_null_outputs(
        polyglot_module=polyglot_module,
        cleaned_sql=cleaned_sql,
        dialect=dialect,
        analysis=analysis,
        column_nullability_by_table=column_nullability_by_table,
        parsed=parsed,
    )
    columns: list[InferredColumn] = []
    lineage_columns: list[CompiledLineageColumnFact] = []
    has_star: bool = _compact_analysis_has_star(analysis)
    infer_nullability: bool = (
        analysis.get(_POLYGLOT_ANALYSIS_SHAPE) != _POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION
    )
    for projection in projections:
        if not isinstance(projection, dict):
            return None
        if bool(projection.get(_POLYGLOT_ANALYSIS_IS_STAR)):
            continue
        output_column: str = str(projection.get(_POLYGLOT_ANALYSIS_NAME) or "")
        if not output_column or output_column == SQL_WILDCARD_TOKEN:
            continue
        columns.append(
            InferredColumn(
                name=output_column,
                type=(
                    cte_passthrough_types.get(output_column)
                    if output_column in direct_cte_outputs
                    else _compact_projection_type(
                        projection=projection, inference_profile=inference_profile
                    )
                ),
                nullability=(
                    InferredNullability.NON_NULL
                    if output_column in filtered_non_null_outputs
                    else (
                        (
                            cte_passthrough_nullability.get(output_column)
                            if output_column in direct_cte_outputs
                            else None
                        )
                        or _compact_projection_nullability(
                            projection=projection,
                            infer_nullability=infer_nullability,
                        )
                    )
                ),
            )
        )
        upstream_columns, confidence = _compact_lineage_upstream_columns(
            projection=projection,
            reference_map=reference_map,
            relation_alias_by_name=relation_alias_by_name,
        )
        transform_kind: ColumnTransformKind = _compact_transform_kind(
            projection=projection,
            has_upstream=bool(upstream_columns),
        )
        lineage_columns.append(
            CompiledLineageColumnFact(
                output_column=output_column,
                upstream_columns=upstream_columns,
                transform_kind=transform_kind,
                confidence=confidence
                if upstream_columns or transform_kind == ColumnTransformKind.CONSTANT
                else ColumnLineageConfidence.UNKNOWN,
            )
        )
    if has_star and len(references) == 1:
        schema_name: str = _analysis_reference_name(references[0])
        declared_order: dict[str, int] = {
            column_name: index
            for index, column_name in enumerate(column_nullability_by_table.get(schema_name, {}))
        }
        fallback_order: int = len(declared_order)
        columns.sort(key=lambda column: declared_order.get(column.name, fallback_order))
        lineage_columns.sort(
            key=lambda column: declared_order.get(column.output_column, fallback_order)
        )
    return tuple(columns), tuple(lineage_columns), has_star


def _compact_analysis_is_eligible(*, analysis: dict[str, Any], projections: list[object]) -> bool:
    shape: object = analysis.get(_POLYGLOT_ANALYSIS_SHAPE)
    if shape not in {_POLYGLOT_ANALYSIS_SHAPE_SELECT, _POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION}:
        return False
    projection: object
    for projection in projections:
        if not isinstance(projection, dict):
            return False
        projection_dict: dict[str, Any] = cast(dict[str, Any], projection)
        transform_kind: str = str(projection_dict.get(_POLYGLOT_ANALYSIS_TRANSFORM_KIND) or "")
        if transform_kind in _POLYGLOT_ANALYSIS_UNSAFE_TRANSFORMS:
            return False
        upstream_values: object = projection_dict.get(_POLYGLOT_ANALYSIS_UPSTREAM)
        if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_CAST and (
            not isinstance(upstream_values, list) or not upstream_values
        ):
            return False
    return True


def _compact_analysis_schema(
    *,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    table_names: frozenset[str] | None = None,
    table_name_aliases: dict[str, str] | None = None,
) -> dict[str, object] | None:
    tables: list[dict[str, object]] = []
    table_name: str
    columns: dict[str, InferredNullability]
    selected_tables: tuple[tuple[str, dict[str, InferredNullability]], ...] = (
        tuple(sorted(column_nullability_by_table.items()))
        if table_names is None
        else tuple(
            (table_name, column_nullability_by_table.get(table_name, {}))
            for table_name in sorted(
                table_names,
                key=lambda name: (table_name_aliases or {}).get(name, name),
            )
        )
    )
    for table_name, columns in selected_tables:
        if not columns:
            continue
        column_types: dict[str, str] = column_types_by_table.get(table_name, {})
        tables.append(
            {
                "name": (table_name_aliases or {}).get(table_name, table_name),
                "columns": [
                    _compact_analysis_schema_column(
                        column_name=column_name,
                        column_type=column_types.get(column_name, "UNKNOWN"),
                        nullability=columns[column_name],
                    )
                    for column_name in columns
                ],
            }
        )
    if not tables:
        return None
    return {"tables": tables}


def _compact_analysis_schema_column(
    *,
    column_name: str,
    column_type: str,
    nullability: InferredNullability,
) -> dict[str, object]:
    column: dict[str, object] = {"name": column_name, "type": column_type}
    if nullability == InferredNullability.NON_NULL:
        column["nullable"] = False
    elif nullability == InferredNullability.NULLABLE:
        column["nullable"] = True
    return column


def _lineage_reference_map(
    references: tuple[CompileSqlReference, ...],
) -> dict[str, tuple[CompiledResourceType, str]]:
    reference_map: dict[str, tuple[CompiledResourceType, str]] = {}
    reference: CompileSqlReference
    for reference in references:
        resource_type: CompiledResourceType | None = _lineage_resource_type(reference)
        if resource_type is None:
            continue
        reference_map[_analysis_reference_name(reference)] = (
            resource_type,
            reference.ref_name,
        )
    return reference_map


def _compact_relation_alias_by_name(analysis: dict[str, Any]) -> dict[str, str | None]:
    alias_by_name: dict[str, str | None] = {}
    relation_key: str
    for relation_key in (_POLYGLOT_ANALYSIS_RELATIONS, _POLYGLOT_ANALYSIS_BASE_TABLES):
        relations: object = analysis.get(relation_key)
        if not isinstance(relations, list):
            continue
        relation: object
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            name: object = relation.get(_POLYGLOT_ANALYSIS_NAME)
            if not isinstance(name, str) or not name:
                continue
            alias: object = relation.get(_POLYGLOT_PAYLOAD_ALIAS)
            alias_by_name[name] = alias if isinstance(alias, str) and alias else None
    return alias_by_name


def _compact_analysis_has_star(analysis: dict[str, Any]) -> bool:
    star_projections: object = analysis.get(_POLYGLOT_ANALYSIS_STAR_PROJECTIONS)
    return isinstance(star_projections, list) and bool(star_projections)


def _compact_projection_type(
    *, projection: dict[str, Any], inference_profile: ExpressionInferenceProfile
) -> str | None:
    cast_type: object = projection.get(_POLYGLOT_ANALYSIS_CAST_TYPE)
    if isinstance(cast_type, str) and cast_type and cast_type != UNKNOWN_SQL_TYPE_NAME:
        return cast_type
    transform_function: object = projection.get(_POLYGLOT_ANALYSIS_TRANSFORM_FUNCTION)
    if isinstance(transform_function, dict):
        function_name: object = transform_function.get(_POLYGLOT_ANALYSIS_FUNCTION_NAME)
        if isinstance(function_name, str):
            declared_type: str | None = inference_profile.function_return_type(function_name)
            if declared_type is not None:
                return declared_type
    type_hint: object = projection.get(_POLYGLOT_ANALYSIS_TYPE_HINT)
    if isinstance(type_hint, str) and type_hint and type_hint != UNKNOWN_SQL_TYPE_NAME:
        return type_hint
    return None


def _compact_projection_nullability(
    *,
    projection: dict[str, Any],
    infer_nullability: bool,
) -> InferredNullability:
    if not infer_nullability:
        return InferredNullability.UNKNOWN
    value: object = projection.get(_POLYGLOT_ANALYSIS_NULLABILITY)
    if value == _POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL:
        return InferredNullability.NON_NULL
    if value == _POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE:
        return InferredNullability.NULLABLE
    return InferredNullability.UNKNOWN


def _compact_lineage_upstream_columns(
    *,
    projection: dict[str, Any],
    reference_map: dict[str, tuple[CompiledResourceType, str]],
    relation_alias_by_name: dict[str, str | None],
) -> tuple[tuple[CompiledLineageSourceFact, ...], ColumnLineageConfidence]:
    upstream_values: object = projection.get(_POLYGLOT_ANALYSIS_UPSTREAM)
    if not isinstance(upstream_values, list):
        return (), ColumnLineageConfidence.UNKNOWN
    columns: list[CompiledLineageSourceFact] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.HIGH
    upstream: object
    for upstream in upstream_values:
        if not isinstance(upstream, dict):
            continue
        column_name: object = upstream.get(_POLYGLOT_PAYLOAD_COLUMN)
        if not isinstance(column_name, str) or not column_name or column_name == SQL_WILDCARD_TOKEN:
            continue
        source_name: object = upstream.get(_POLYGLOT_ANALYSIS_SOURCE_NAME) or upstream.get(
            _POLYGLOT_ANALYSIS_TABLE
        )
        if not isinstance(source_name, str) or not source_name:
            confidence = ColumnLineageConfidence.UNKNOWN
            continue
        resource: tuple[CompiledResourceType, str] | None = reference_map.get(source_name)
        if resource is None:
            continue
        source_confidence: object = upstream.get(_POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE)
        source_alias: object = upstream.get(_POLYGLOT_ANALYSIS_SOURCE_ALIAS)
        if source_confidence != RESOLVED_SOURCE_CONFIDENCE and not isinstance(source_alias, str):
            confidence = ColumnLineageConfidence.MEDIUM
        resource_type, resource_name = resource
        key: tuple[CompiledResourceType, str, str] = (resource_type, resource_name, column_name)
        if key in seen:
            continue
        seen.add(key)
        columns.append(
            CompiledLineageSourceFact(
                resource_type=resource_type,
                resource_name=resource_name,
                column_name=column_name,
            )
        )
    return tuple(
        sorted(
            columns,
            key=lambda column: (
                column.resource_type.value,
                column.resource_name,
                column.column_name,
            ),
        )
    ), confidence


def _compact_transform_kind(
    *, projection: dict[str, Any], has_upstream: bool
) -> ColumnTransformKind:
    transform_kind: str = str(projection.get(_POLYGLOT_ANALYSIS_TRANSFORM_KIND) or "")
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_STAR:
        return ColumnTransformKind.STAR
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_CAST:
        return ColumnTransformKind.CAST
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION:
        return ColumnTransformKind.AGGREGATION
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT or not has_upstream:
        return ColumnTransformKind.CONSTANT
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_DIRECT:
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION
