"""Model analysis state that publishes producer shapes as each analysis completes."""

from __future__ import annotations

import contextvars
import heapq
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from graphlib import CycleError, TopologicalSorter

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.cache import model_analysis_output_signature
from sqlbuild.compiler.compile._helpers.analysis.compact import serialized_analysis
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    binding_relation_names,
    published_model_shape,
    referenced_model_names,
)
from sqlbuild.compiler.compile.classes.stored_model_analyses import dependencies_current
from sqlbuild.compiler.compile.models import (
    DataflowReuse,
    ModelSqlAnalysis,
    ModelSqlAnalysisRequest,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.presentation.main.transient_line_coordinator import (
    shared_transient_line_coordinator,
)

_WORKER_POLL_SECONDS: float = 0.05
_WORKER_START_GRACE_SECONDS: float = 1.0
_INTERRUPT_NOTICE: str = "Interrupted; finishing in-flight model analysis...\n"


class BindingDataflow:
    """Analyze each model with exactly the producer shapes and cache state it depends on."""

    def __init__(
        self,
        *,
        requests: tuple[ModelSqlAnalysisRequest, ...],
        names: tuple[str, ...],
        reuse: DataflowReuse,
        shapes: dict[str, dict[str, str]],
        types: dict[str, dict[str, str]],
        nullability: dict[str, dict[str, InferredNullability]],
        profile: ExpressionInferenceProfile,
        analyze: Callable[..., tuple[ModelSqlAnalysis, ...]],
        complete: Callable[..., tuple[ModelSqlAnalysis, ...]],
    ) -> None:
        self._requests: tuple[ModelSqlAnalysisRequest, ...] = requests
        self._names: tuple[str, ...] = names
        self._by_name: dict[str, ModelSqlAnalysisRequest] = dict(zip(names, requests, strict=True))
        served_keys: frozenset[str | None] = frozenset(
            self._by_name[name].cache_key for name in reuse.served if name in self._by_name
        )
        self._cached: dict[str, PolyglotAnalysisResult] = {
            key: analysis for key, analysis in reuse.cached.items() if key not in served_keys
        }
        self._served: dict[str, dict[str, str]] = reuse.served
        self._signatures: dict[str, str] = {}
        available_names: frozenset[str] = frozenset(names)
        self._dependencies: dict[str, tuple[str, ...]] = {
            name: referenced_model_names(
                model_input=request.model_input, available_names=available_names
            )
            for name, request in self._by_name.items()
        }
        self._previous_signatures: dict[str, str] = reuse.previous_signatures
        self._complete_shapes: dict[str, dict[str, str]] = dict(shapes)
        self._available_types: dict[str, dict[str, str]] = dict(types)
        self._available_nullability: dict[str, dict[str, InferredNullability]] = dict(nullability)
        self._reusable: dict[str, PolyglotAnalysisResult] = dict(reuse.cached)
        self._profile: ExpressionInferenceProfile = profile
        self._analyze: Callable[..., tuple[ModelSqlAnalysis, ...]] = analyze
        self._complete: Callable[..., tuple[ModelSqlAnalysis, ...]] = complete
        self._changed: set[str] = set()
        self._results: dict[str, ModelSqlAnalysis] = {}
        self._ready: list[tuple[int, int, str]] = []
        self._pending: dict[str, int] = {}
        self._dependents: dict[str, list[str]] = {}
        self._failure: BaseException | None = None
        self._cancelled: bool = False
        self._condition: threading.Condition = threading.Condition(threading.Lock())

    def analyze_waves(
        self,
    ) -> tuple[tuple[ModelSqlAnalysis, ...], dict[str, PolyglotAnalysisResult]]:
        """Analyze one topological level at a time, the reference schedule."""

        sorter: TopologicalSorter[str] = TopologicalSorter(self._dependencies)
        try:
            sorter.prepare()
        except CycleError:
            return self._analyze_cycle(), self._cached
        while sorter.is_active():
            ready: tuple[str, ...] = tuple(sorter.get_ready())
            self._analyze_ready(ready)
            sorter.done(*ready)
        return tuple(self._results[name] for name in self._names), self._reusable

    def analyze_dataflow(
        self, *, workers: int, batch_min: int, batch_limit: int
    ) -> tuple[tuple[ModelSqlAnalysis, ...], dict[str, PolyglotAnalysisResult]] | None:
        """Analyze models as their producers finish; return None after an analysis error."""

        try:
            order: tuple[str, ...] = tuple(TopologicalSorter(self._dependencies).static_order())
        except CycleError:
            return self._analyze_cycle(), self._cached
        heights: dict[str, int] = {}
        self._dependents = {name: [] for name in self._by_name}
        for name in self._by_name:
            for parent in self._dependencies[name]:
                self._dependents[parent].append(name)
        for name in reversed(order):
            heights[name] = 1 + max((heights[child] for child in self._dependents[name]), default=0)
        priorities: dict[str, tuple[int, int]] = {
            name: (-heights[name], position) for position, name in enumerate(self._by_name)
        }
        self._pending = {name: len(self._dependencies[name]) for name in self._by_name}
        self._ready = [
            (*priorities[name], name) for name in self._by_name if not self._pending[name]
        ]
        heapq.heapify(self._ready)
        share: tuple[int, int, int] = (workers, batch_min, batch_limit)
        with serialized_analysis(self._condition):
            context: contextvars.Context = contextvars.copy_context()
        threads: list[threading.Thread] = [
            threading.Thread(
                target=context.copy().run,
                args=(self._run_worker,),
                kwargs={"priorities": priorities, "share": share},
                name=f"sqlbuild-model-analysis-{index}",
                daemon=True,
            )
            for index in range(max(1, workers))
        ]
        self._wait_for_workers(threads)
        if self._failure is not None and not isinstance(self._failure, Exception):
            raise self._failure
        if self._failure is not None:
            return None
        return tuple(self._results[name] for name in self._names), self._reusable

    def _wait_for_workers(self, threads: list[threading.Thread]) -> None:
        """Join workers lock-free; a first interrupt cancels them, repeats wait for their exit."""

        attempted: list[threading.Thread] = []
        interrupt: BaseException | None = None
        try:
            for thread in threads:
                attempted.append(thread)
                thread.start()
        except BaseException as error:  # noqa: BLE001 - re-raised after workers stop
            interrupt = self._cancel(interrupt=None, error=error)
        pending: list[threading.Thread] = list(attempted)
        unstarted_deadline: float = time.monotonic() + _WORKER_START_GRACE_SECONDS
        while pending:
            try:
                pending = [
                    thread
                    for thread in pending
                    if self._worker_running(thread=thread, unstarted_deadline=unstarted_deadline)
                ]
            except BaseException as error:  # noqa: BLE001 - re-raised after workers stop
                interrupt = self._cancel(interrupt=interrupt, error=error)
        if interrupt is not None:
            raise interrupt

    def _cancel(self, *, interrupt: BaseException | None, error: BaseException) -> BaseException:
        if interrupt is not None:
            return interrupt
        self._cancelled = True
        if not isinstance(error, Exception):
            shared_transient_line_coordinator().write_persistent(
                stream=sys.stderr, text=_INTERRUPT_NOTICE
            )
        return error

    @staticmethod
    def _worker_running(*, thread: threading.Thread, unstarted_deadline: float) -> bool:
        """Join briefly; a thread whose OS thread never started is dropped after a grace period."""

        if thread.ident is None:
            time.sleep(_WORKER_POLL_SECONDS / 10)
            return time.monotonic() < unstarted_deadline
        try:
            thread.join(_WORKER_POLL_SECONDS)
        except RuntimeError:
            return True
        return thread.is_alive()

    def _run_worker(
        self, *, priorities: dict[str, tuple[int, int]], share: tuple[int, int, int]
    ) -> None:
        with self._condition:
            try:
                self._drain_ready(priorities=priorities, share=share)
            except BaseException as error:  # noqa: BLE001 - re-raised or replayed in waves
                self._record_failure(error)
            self._condition.notify_all()

    def _record_failure(self, error: BaseException) -> None:
        """Keep the first failure, except that a non-Exception interrupt always wins."""

        if self._failure is None or (
            isinstance(self._failure, Exception) and not isinstance(error, Exception)
        ):
            self._failure = error

    def _drain_ready(
        self, *, priorities: dict[str, tuple[int, int]], share: tuple[int, int, int]
    ) -> None:
        workers, batch_min, batch_limit = share
        while (
            not self._cancelled
            and self._failure is None
            and len(self._results) < len(self._by_name)
        ):
            if not self._ready:
                _ = self._condition.wait(_WORKER_POLL_SECONDS)
                continue
            count: int = min(
                len(self._ready),
                max(batch_min, -(-len(self._ready) // workers)),
                batch_limit,
            )
            batch: tuple[str, ...] = tuple(heapq.heappop(self._ready)[2] for _ in range(count))
            self._analyze_ready(batch)
            for name in batch:
                for child in self._dependents[name]:
                    self._pending[child] -= 1
                    if not self._pending[child]:
                        heapq.heappush(self._ready, (*priorities[child], child))
            self._condition.notify_all()

    def _analyze_cycle(self) -> tuple[ModelSqlAnalysis, ...]:
        return self._complete(
            requests=self._requests,
            analyses=self._analyze(
                requests=self._requests,
                cached_analyses=self._cached,
                column_types_by_table=self._available_types,
                column_nullability_by_table=self._available_nullability,
            ),
            complete_binding_schemas=self._complete_shapes,
        )

    def _analyze_ready(self, ready: tuple[str, ...]) -> None:
        wave: list[ModelSqlAnalysisRequest] = []
        for name in ready:
            request: ModelSqlAnalysisRequest = self._by_name[name]
            if any(parent in self._changed for parent in self._dependencies[name]):
                self._changed.add(name)
                if request.cache_key is not None:
                    self._reusable.pop(request.cache_key, None)
            if not self._served_parents_final(name) and request.cache_key is not None:
                self._reusable.pop(request.cache_key, None)
            bindings: dict[str, dict[str, str]] | None = (
                None
                if request.binding_schema is None
                else {
                    relation: self._complete_shapes.get(relation, {})
                    for relation in binding_relation_names(request.model_input.references)
                }
            )
            wave.append(replace(request, binding_schema=bindings))
        wave_requests: tuple[ModelSqlAnalysisRequest, ...] = tuple(wave)
        wave_names: set[str] = set(ready)
        for request in wave_requests:
            wave_names.update(binding_relation_names(request.model_input.references))
        analyses: tuple[ModelSqlAnalysis, ...] = self._complete(
            requests=wave_requests,
            analyses=self._analyze(
                requests=wave_requests,
                cached_analyses=self._reusable,
                column_types_by_table=self._available_types,
                column_nullability_by_table=self._available_nullability,
            ),
            complete_binding_schemas={
                name: self._complete_shapes[name]
                for name in wave_names
                if name in self._complete_shapes
            },
            supplied_relations=frozenset(
                name
                for name in wave_names
                if name in self._complete_shapes
                and self._available_types.get(name, {}).keys() == self._complete_shapes[name].keys()
            ),
        )
        for name, request, result in zip(ready, wave_requests, analyses, strict=True):
            self._results[name] = result
            self._publish(name=name, request=request, result=result)

    def _served_parents_final(self, name: str) -> bool:
        """Return whether a stored analysis, if served, was made from the parents' final state."""

        dependencies: dict[str, str] | None = self._served.get(name)
        return dependencies is None or dependencies_current(
            dependencies=dependencies,
            parent_signatures={
                parent: self._signatures.get(parent) for parent in self._dependencies[name]
            },
        )

    def _publish(
        self, *, name: str, request: ModelSqlAnalysisRequest, result: ModelSqlAnalysis
    ) -> None:
        analysis: PolyglotAnalysisResult = result.polyglot_analysis
        signature: str = model_analysis_output_signature(analysis)
        self._signatures[name] = signature
        if signature != self._previous_signatures.get(name):
            self._changed.add(name)
        required: frozenset[str] = binding_relation_names(request.model_input.references)
        star_known: bool = not analysis.has_star or (
            analysis.star_resolved and required <= self._complete_shapes.keys()
        )
        if not analysis.columns or not star_known:
            return
        shape: dict[str, str] = published_model_shape(
            sql=result.cleaned_sql or request.query_sql,
            columns={column.name: column.type or "UNKNOWN" for column in analysis.columns},
            inputs={table: self._complete_shapes.get(table, {}) for table in required},
            profile=self._profile,
            config_values=request.model_input.config.values,
        )
        self._complete_shapes.setdefault(name, shape)
        self._available_types.setdefault(name, shape)
        self._available_nullability.setdefault(
            name, dict.fromkeys(shape, InferredNullability.UNKNOWN)
        )
