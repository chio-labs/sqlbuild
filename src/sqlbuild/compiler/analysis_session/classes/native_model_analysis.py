"""One compile's native model analysis session, with Python's catalog and metric bookkeeping."""

from __future__ import annotations

import logging
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.analysis_session.constants import (
    NATIVE_ANALYSIS_FAILURE_MESSAGE,
    NATIVE_ANALYSIS_STORE_FAILURE_MESSAGE,
)
from sqlbuild.compiler.analysis_session.models import (
    NativeModelAnalyses,
    NativeModelAnalysisRequest,
)
from sqlbuild.compiler.analysis_session.types import FinishRow, ShapeRows, StepRow
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.compile")


class NativeModelAnalysis:
    """Drive one native session; its outcomes stay native for compiled model assembly."""

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

    def analyses(self, session: _native.NativeModelAnalysisSession) -> NativeModelAnalyses:
        """Every model's session position by name; a native internal failure raises."""

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
        schema_additions, analysis_names, succeeded = finished
        self._record_catalog_changes(
            schema_additions=schema_additions, analysis_names=analysis_names
        )
        self._record_cache(session)
        names: tuple[str, ...] = tuple(
            request.model_input.model_file.file_path.stem for request in self._python.requests
        )
        return NativeModelAnalyses(
            positions={name: position for position, name in enumerate(names)},
            succeeded=frozenset(
                name for name, success in zip(names, succeeded, strict=True) if success
            ),
            session=session,
        )

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
