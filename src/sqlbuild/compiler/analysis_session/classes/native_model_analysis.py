"""One compile's native model analysis, read into Python's analysis objects."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.analysis_session._helpers.session_rows import (
    binding_diagnostics,
    compact_lineage,
    contract_proof,
    lineage_facts,
)
from sqlbuild.compiler.analysis_session.constants import (
    LINEAGE_NATIVE,
    NATIVE_ANALYSIS_FAILURE_MESSAGE,
    NATIVE_ANALYSIS_STORE_FAILURE_MESSAGE,
)
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.analysis_session.types import (
    ColumnRow,
    FinishRow,
    OutcomeRow,
    ProofRow,
    ShapeRows,
    StepRow,
)
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    InferredColumn,
    ModelSqlAnalysis,
    ModelSqlAnalysisRequest,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.compile")


class NativeModelAnalysis:
    """Drive one native session and read its outcomes as Python's analyses."""

    def __init__(
        self,
        *,
        request: NativeModelAnalysisRequest,
        python: PythonModelAnalysis,
        catalog: Any,
    ) -> None:
        self._python: PythonModelAnalysis = python
        self._catalog: Any = catalog
        self._types: dict[str, dict[str, str]] = dict(request.column_types_by_table)
        self._nullability: dict[str, dict[str, InferredNullability]] = dict(
            request.column_nullability_by_table
        )
        self._columns: dict[ColumnRow, InferredColumn] = {}

    def analyses(self, session: _native.NativeModelAnalysisSession) -> dict[str, ModelSqlAnalysis]:
        """Every model's analysis by name; a native internal failure raises."""

        step: StepRow = session.run()
        publications, failures = step
        for failure in failures:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message=NATIVE_ANALYSIS_FAILURE_MESSAGE,
                sqlbuild_error=failure,
            )
        self._publish(publications)
        finished: FinishRow = session.finish()
        outcomes, schema_additions, analysis_names, contracts = finished
        self._record_catalog_changes(
            schema_additions=schema_additions, analysis_names=analysis_names
        )
        self._record_cache(session)
        return {
            request.model_input.model_file.file_path.stem: self._model_analysis(
                request=request, outcome=outcome, contract=contract
            )
            for request, outcome, (_, contract) in zip(
                self._python.requests, outcomes, contracts, strict=True
            )
        }

    def _record_cache(self, session: _native.NativeModelAnalysisSession) -> None:
        stats: tuple[int, int, int, str | None] | None = session.cache_stats
        if stats is None:
            self._python.record_uncached()
            return
        hits, misses, _, failure = stats
        if failure is not None:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message=NATIVE_ANALYSIS_STORE_FAILURE_MESSAGE,
                sqlbuild_error=failure,
            )
        if hits + misses == 0:
            self._python.record_uncached()
            return
        self._python.record_cached(hits=hits, misses=misses)

    def _publish(self, publications: ShapeRows) -> None:
        for name, shape in publications:
            published: dict[str, str] = dict(shape)
            self._types.setdefault(name, published)
            self._nullability.setdefault(
                name, dict.fromkeys(published, InferredNullability.UNKNOWN)
            )

    def _record_catalog_changes(
        self, *, schema_additions: ShapeRows, analysis_names: list[str]
    ) -> None:
        """Leave Python's binding catalog as its own analysis would have."""

        additions: dict[str, dict[str, str]] = {
            name: dict(shape)
            for name, shape in schema_additions
            if name not in self._catalog.schemas
        }
        self._catalog.schemas.update(additions)
        if additions:
            self._catalog.native.update_relations(additions)
        self._catalog.prepare_analysis(
            types={name: self._types[name] for name in analysis_names if name in self._types},
            nullability={
                name: self._nullability[name]
                for name in analysis_names
                if name in self._nullability
            },
        )

    def _inferred_columns(self, rows: list[ColumnRow] | None) -> tuple[InferredColumn, ...] | None:
        """Columns as Python's analysis shares them: one object per distinct column value."""

        if rows is None:
            return None
        return tuple(map(self._inferred_column, rows))

    def _inferred_column(self, row: ColumnRow) -> InferredColumn:
        column: InferredColumn | None = self._columns.get(row)
        if column is None:
            name, data_type, nullability = row
            column = InferredColumn(
                name=name, type=data_type, nullability=InferredNullability(nullability)
            )
            self._columns[row] = column
        return column

    def _model_analysis(
        self,
        *,
        request: ModelSqlAnalysisRequest,
        outcome: OutcomeRow,
        contract: ProofRow | None,
    ) -> ModelSqlAnalysis:
        (
            succeeded,
            columns,
            lineage_source,
            lineage_rows,
            has_star,
            star_resolved,
            diagnostics,
            validated,
            cleaned_sql,
        ) = outcome
        lineage: Sequence[CompiledLineageColumnFact] = (
            (compact_lineage(lineage_rows) if succeeded else ())
            if lineage_source == LINEAGE_NATIVE
            else lineage_facts(lineage_rows)
        )
        return ModelSqlAnalysis(
            polyglot_analysis=PolyglotAnalysisResult(
                analysis_succeeded=succeeded,
                columns=self._inferred_columns(columns),
                lineage_columns=lineage,
                has_star=has_star,
                star_resolved=star_resolved,
                binding_diagnostics=binding_diagnostics(diagnostics),
                binding_validated=validated,
            ),
            placeholders=request.placeholders,
            fused_binding_validated=True,
            cleaned_sql=cleaned_sql,
            validated_schema=request.binding_schema,
            dynamic_column_contract=contract_proof(contract),
        )
