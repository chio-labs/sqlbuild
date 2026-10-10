"""Python's half of native model analysis: per-model request rows and deferred analyses."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.cache import record_analysis_cache_metrics
from sqlbuild.compiler.compile._helpers.analysis.columns import (
    substitute_placeholder_defaults,
    table_function_analysis_name,
)
from sqlbuild.compiler.compile._helpers.analysis.compact import (
    analyze_columns_and_lineage_with_polyglot,
)
from sqlbuild.compiler.compile._helpers.analysis.set_operations import names_set_operation
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    binding_relation_names,
    binding_schema_for_model,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
)
from sqlbuild.compiler.compile._helpers.sharing.binding import lineage_reference_map
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompileSqlReference,
    ModelSqlAnalysisRequest,
    NativeCompactAnalysis,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.planner.constants import (
    SNAPSHOT_DEFAULT_VALID_FROM_COLUMN,
    SNAPSHOT_DEFAULT_VALID_TO_COLUMN,
)
from sqlbuild.compiler.planner.types import ContractPolicy, MaterializationType
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


class PythonModelAnalysis:
    """The analysed models' request facts, and today's Python analysis where native defers."""

    def __init__(
        self,
        *,
        model_inputs: tuple[CompileModelInput, ...],
        inference_profile: ExpressionInferenceProfile,
        complete_binding_schemas: dict[str, dict[str, str]],
    ) -> None:
        self._profile: ExpressionInferenceProfile = inference_profile
        self.requests: tuple[ModelSqlAnalysisRequest, ...] = tuple(
            ModelSqlAnalysisRequest(
                model_input=model_input,
                query_sql=cursor_intrinsics_analysis_sql(
                    sql=model_input.query_sql,
                    cursor_type=model_input.config.values.get("cursor_type"),
                ),
                placeholders=_placeholders(model_input),
                cache_key=None,
                binding_schema=binding_schema_for_model(
                    model_input=model_input, complete_binding_schemas=complete_binding_schemas
                ),
            )
            for model_input in model_inputs
        )

    def model_rows(self) -> list[tuple[object, ...]]:
        """Each model's native request row, in analysis order."""

        return [_model_row(request) for request in self.requests]

    def analyze_deferred(
        self,
        *,
        model: int,
        precomputed: NativeCompactAnalysis,
        binding_schema: dict[str, dict[str, str]],
        column_types_by_table: dict[str, dict[str, str]],
        column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    ) -> PolyglotAnalysisResult:
        """Python's legacy analysis of a model the native engine handed back."""

        request: ModelSqlAnalysisRequest = self.requests[model]
        return analyze_columns_and_lineage_with_polyglot(
            query_sql=request.query_sql,
            references=request.model_input.references,
            placeholders=request.placeholders,
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            inference_profile=self._profile,
            allow_compact_analysis=True,
            binding_schema=binding_schema,
            recover_cte_facts=_recovers_cte_facts(request.model_input),
            precomputed=precomputed,
        )

    def enrich(
        self, *, model: int, input_schemas: dict[str, dict[str, str]]
    ) -> PolyglotAnalysisResult:
        """Python's re-analysis of a model with its known input shapes."""

        request: ModelSqlAnalysisRequest = self.requests[model]
        return analyze_columns_and_lineage_with_polyglot(
            query_sql=request.query_sql,
            references=request.model_input.references,
            placeholders=request.placeholders,
            column_types_by_table=input_schemas,
            column_nullability_by_table={
                table: dict.fromkeys(columns, InferredNullability.UNKNOWN)
                for table, columns in input_schemas.items()
            },
            inference_profile=self._profile,
            allow_compact_analysis=True,
            recover_cte_facts=_recovers_cte_facts(request.model_input),
        )

    @staticmethod
    def family_row(family: SchemaDynamicColumnFamily) -> tuple[str, str, str, str, str, str | None]:
        """One declared dynamic column family as the native request row."""

        return (
            family.name,
            family.pivot_column,
            family.value_column,
            family.aggregate,
            family.type,
            family.name_pattern,
        )

    @staticmethod
    def legacy_precomputed(
        *,
        cleaned_sql: str,
        binding_diagnostics: tuple[SqlBindingDiagnostic, ...],
        lineage: list[tuple[str, int, int, list[tuple[str, str, str]]]] | None,
    ) -> NativeCompactAnalysis:
        """The native result Python's legacy analysis reads, with lineage rows when kept."""

        if lineage is None:
            return NativeCompactAnalysis(
                cleaned_sql=cleaned_sql,
                analysis=None,
                projected=False,
                binding_diagnostics=binding_diagnostics,
            )
        pool: dict[str, int] = {}
        facts: list[object] = []
        for output_column, transform_code, confidence_code, sources in lineage:
            name_index: int = pool.setdefault(output_column, len(pool))
            source_indexes: list[list[int]] = []
            for source in sources:
                source_indexes.append([pool.setdefault(value, len(pool)) for value in source])
            facts.append([name_index, None, 0, transform_code, confidence_code, source_indexes])
        return NativeCompactAnalysis(
            cleaned_sql=cleaned_sql,
            analysis=None,
            projected=False,
            binding_diagnostics=binding_diagnostics,
            compact_rows=list(range(len(facts))),
            compact_fact_rows=facts,
            string_pool=tuple(pool),
            compact_column_cache={},
            compact_template_index=0,
            compact_fact_cache={},
            compact_decoded_fact_cache={},
        )

    def record_uncached(self) -> None:
        """Record that every analysed model bypassed the analysis cache."""

        record_analysis_cache_metrics(
            batch_hits=0, entry_hits=0, misses=0, bypasses=len(self.requests)
        )


def _model_row(request: ModelSqlAnalysisRequest) -> tuple[object, ...]:
    model_input: CompileModelInput = request.model_input
    references: tuple[CompileSqlReference, ...] = model_input.references
    values: dict[str, object] = model_input.config.values
    return (
        model_input.model_file.file_path.stem,
        request.query_sql,
        list((request.placeholders or {}).items()),
        [
            (_analysis_name(reference), reference.ref_kind == SqlReferenceKind.REF)
            for reference in references
        ],
        [
            (name, resource_type.value, resource_name)
            for name, (resource_type, resource_name) in lineage_reference_map(references).items()
        ],
        sorted(binding_relation_names(references)),
        _recovers_cte_facts(model_input),
        names_set_operation(request.query_sql),
        (
            (
                str(values.get("valid_from_column") or SNAPSHOT_DEFAULT_VALID_FROM_COLUMN),
                str(values.get("valid_to_column") or SNAPSHOT_DEFAULT_VALID_TO_COLUMN),
            )
            if values.get("materialized") == MaterializationType.SNAPSHOT
            else None
        ),
        (
            substitute_placeholder_defaults(
                query_sql=request.query_sql, placeholders=request.placeholders
            )
            if request.placeholders
            else request.query_sql
        ),
        [
            PythonModelAnalysis.family_row(family)
            for family in (
                model_input.schema_entry.dynamic_columns
                if model_input.schema_entry is not None
                else ()
            )
        ],
    )


def _analysis_name(reference: CompileSqlReference) -> str:
    if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return table_function_analysis_name(reference.ref_name)
    return reference.ref_name


def _placeholders(model_input: CompileModelInput) -> dict[str, str] | None:
    raw_placeholders: object | None = model_input.config.values.get("placeholders")
    return (
        {str(key): str(value) for key, value in raw_placeholders.items()}
        if isinstance(raw_placeholders, dict)
        else None
    )


def _recovers_cte_facts(model_input: CompileModelInput) -> bool:
    return model_input.config.values.get("contract") == ContractPolicy.ENFORCED or (
        model_input.schema_entry is not None and bool(model_input.schema_entry.type_enforcement)
    )
