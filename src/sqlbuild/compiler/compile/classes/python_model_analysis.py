"""Python's half of native model analysis: per-model request rows and cache metrics."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.cache import record_analysis_cache_metrics
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    binding_schema_for_model,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
)
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysisRequest,
)
from sqlbuild.compiler.compile.types import ModelInput
from sqlbuild.compiler.planner.constants import (
    SNAPSHOT_DEFAULT_VALID_FROM_COLUMN,
    SNAPSHOT_DEFAULT_VALID_TO_COLUMN,
)
from sqlbuild.compiler.planner.types import ContractPolicy, MaterializationType
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


class PythonModelAnalysis:
    """The analysed models' request facts."""

    def __init__(
        self,
        *,
        model_inputs: tuple[ModelInput, ...],
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

    def record_cached(self, *, hits: int, misses: int) -> None:
        """Record the analysis cache entries a native session read and missed."""

        record_analysis_cache_metrics(batch_hits=0, entry_hits=hits, misses=misses, bypasses=0)

    def record_uncached(self) -> None:
        """Record that every analysed model bypassed the analysis cache."""

        record_analysis_cache_metrics(
            batch_hits=0, entry_hits=0, misses=0, bypasses=len(self.requests)
        )


def _model_row(request: ModelSqlAnalysisRequest) -> tuple[object, ...]:
    model_input: ModelInput = request.model_input
    rows: list[tuple[str, str, str | None, int | None]] = model_input.reference_rows
    values: dict[str, object] = model_input.config.values
    return (
        model_input.model_file.file_path.stem,
        request.query_sql,
        list((request.placeholders or {}).items()),
        [(str(kind), name) for kind, name, _, _ in rows],
        _recovers_cte_facts(model_input),
        (
            (
                str(values.get("valid_from_column") or SNAPSHOT_DEFAULT_VALID_FROM_COLUMN),
                str(values.get("valid_to_column") or SNAPSHOT_DEFAULT_VALID_TO_COLUMN),
            )
            if values.get("materialized") == MaterializationType.SNAPSHOT
            else None
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


def _placeholders(model_input: ModelInput) -> dict[str, str] | None:
    raw_placeholders: object | None = model_input.config.values.get("placeholders")
    return (
        {str(key): str(value) for key, value in raw_placeholders.items()}
        if isinstance(raw_placeholders, dict)
        else None
    )


def _recovers_cte_facts(model_input: ModelInput) -> bool:
    return model_input.config.values.get("contract") == ContractPolicy.ENFORCED or (
        model_input.schema_entry is not None and bool(model_input.schema_entry.type_enforcement)
    )
