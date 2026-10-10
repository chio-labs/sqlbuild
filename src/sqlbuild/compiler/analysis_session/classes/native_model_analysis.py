"""One compile's native model analysis, with Python answering the session's deferrals."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.session_rows import (
    binding_diagnostics,
    compact_lineage,
    contract_proof,
    deferred_row,
    lineage_facts,
)
from sqlbuild.compiler.analysis_session.constants import (
    CONTRACT_DEFERRED,
    DEFERRAL_ANALYSIS,
    DEFERRAL_DYNAMIC_PIVOT,
    DEFERRAL_ENRICHMENT,
    DEFERRAL_LEGACY_ANALYSIS,
    DEFERRAL_SESSION,
    LINEAGE_FACTS,
    LINEAGE_NATIVE,
    NATIVE_ANALYSIS_FAILURE_MESSAGE,
    NATIVE_ANALYSIS_STORE_FAILURE_MESSAGE,
    NATIVE_SESSION_FAILURE_MESSAGE,
)
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.analysis_session.types import (
    ColumnRow,
    DeferralRow,
    DeferredRow,
    FinishRow,
    OutcomeRow,
    ProofRow,
    ShapeRows,
    StepRow,
)
from sqlbuild.compiler.compile._helpers.analysis.cache import record_analysis_cache_metrics
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
    """Drive one native session, answering deferrals with today's Python analysis."""

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
        self._kept: dict[tuple[int, str], PolyglotAnalysisResult] = {}
        self._columns: dict[ColumnRow, InferredColumn] = {}
        self._deferrals: Counter[str] = Counter()

    def analyses(
        self, session: _native.NativeModelAnalysisSession
    ) -> dict[str, ModelSqlAnalysis] | None:
        """Every model's analysis by name, or None when Python must analyse them all."""

        finished: FinishRow | None = self._finished(session)
        if finished is None:
            record_analysis_deferral(kind=DEFERRAL_SESSION)
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message=NATIVE_SESSION_FAILURE_MESSAGE,
                sqlbuild_error=session.failure,
            )
            return None
        outcomes, schema_additions, analysis_names, contracts = finished
        self._record_catalog_changes(
            schema_additions=schema_additions, analysis_names=analysis_names
        )
        self._deferrals[DEFERRAL_DYNAMIC_PIVOT] += sum(
            kind == CONTRACT_DEFERRED for kind, _ in contracts
        )
        for kind, count in self._deferrals.items():
            record_analysis_deferral(kind=kind, count=count)
        self._record_cache(session)
        return {
            request.model_input.model_file.file_path.stem: self._model_analysis(
                index=index, request=request, outcome=outcome, contract=contract
            )
            for index, (request, outcome, (_, contract)) in enumerate(
                zip(self._python.requests, outcomes, contracts, strict=True)
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
        record_analysis_cache_metrics(batch_hits=0, entry_hits=hits, misses=misses, bypasses=0)

    def _finished(self, session: _native.NativeModelAnalysisSession) -> FinishRow | None:
        step: StepRow | None = session.run()
        while step is not None:
            publications, deferrals, failures = step
            for failure in failures:
                log_debug_event(
                    logger=_DEBUG_LOGGER,
                    message=NATIVE_ANALYSIS_FAILURE_MESSAGE,
                    sqlbuild_error=failure,
                )
            self._publish(publications)
            if not deferrals:
                return session.finish()
            answers: list[DeferredRow] = [self._answer(deferral) for deferral in deferrals]
            if not session.provide(answers):
                return None
            step = session.run()
        return None

    def _publish(self, publications: ShapeRows) -> None:
        for name, shape in publications:
            published: dict[str, str] = dict(shape)
            self._types.setdefault(name, published)
            self._nullability.setdefault(
                name, dict.fromkeys(published, InferredNullability.UNKNOWN)
            )

    def _answer(self, deferral: DeferralRow) -> DeferredRow:
        kind, model, cleaned_sql, schemas, diagnostics, lineage = deferral
        shapes: dict[str, dict[str, str]] = {name: dict(shape) for name, shape in schemas}
        analysis: PolyglotAnalysisResult
        if kind == DEFERRAL_ANALYSIS:
            self._deferrals[DEFERRAL_LEGACY_ANALYSIS] += 1
            analysis = self._python.analyze_deferred(
                model=model,
                precomputed=PythonModelAnalysis.legacy_precomputed(
                    cleaned_sql=cleaned_sql or "",
                    binding_diagnostics=binding_diagnostics(diagnostics),
                    lineage=lineage,
                ),
                binding_schema=shapes,
                column_types_by_table=self._types,
                column_nullability_by_table=self._nullability,
            )
        else:
            self._deferrals[DEFERRAL_ENRICHMENT] += 1
            analysis = self._python.enrich(model=model, input_schemas=shapes)
        self._kept[(model, kind)] = analysis
        return deferred_row(model=model, analysis=analysis)

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
        index: int,
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
            if lineage_source == LINEAGE_FACTS
            else self._kept[(index, lineage_source)].lineage_columns
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
