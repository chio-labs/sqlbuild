"""Serve unchanged models' analyses from the previous compile instead of the analysis cache."""

from __future__ import annotations

import hashlib
from collections import Counter

import orjson

from sqlbuild.compiler.compile._helpers.analysis.cache import (
    model_analysis_output_signature,
    read_model_analyses,
    write_model_analyses,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import referenced_model_names
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompileModelInput,
    ModelAnalysisCaching,
    ModelSqlAnalysisRequest,
    PolyglotAnalysisResult,
    StoredAnalysisScope,
    StoredModelAnalysis,
)
from sqlbuild.compiler.compile.types import ModelAnalysisReuse
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.profiling.main._metric import record_compile_metric
from sqlbuild.compiler.profiling.main.record import record_compile_timing


class StoredModelAnalyses:
    """Analyses a compile may serve from the previous compile, and what it records for the next."""

    def __init__(
        self,
        *,
        caching: ModelAnalysisCaching | None,
        requests: tuple[ModelSqlAnalysisRequest, ...],
        column_types_by_table: dict[str, dict[str, str]],
        column_nullability_by_table: dict[str, dict[str, InferredNullability]],
        complete_binding_schemas: dict[str, dict[str, str]],
    ) -> None:
        self._scope: StoredAnalysisScope | None = _stored_analysis_scope(
            caching=caching,
            requests=requests,
            column_types_by_table=column_types_by_table,
            column_nullability_by_table=column_nullability_by_table,
            complete_binding_schemas=complete_binding_schemas,
        )

    @property
    def served(self) -> dict[str, StoredModelAnalysis]:
        """Return stored analyses that may serve their own model, whose cache key no other uses."""

        return {} if self._scope is None else self._scope.stored

    def stale_names(
        self,
        *,
        requests: tuple[ModelSqlAnalysisRequest, ...],
        cached: dict[str, PolyglotAnalysisResult],
        current_signatures: dict[str, str],
    ) -> set[str]:
        """Return served models whose parents' final signatures differ from their stored ones."""

        analyzed_names: frozenset[str] = frozenset(
            _name(request.model_input) for request in requests
        )
        served: dict[str, StoredModelAnalysis] = self.served
        return {
            name
            for request in requests
            if (name := _name(request.model_input)) in served
            and request.cache_key is not None
            and cached.get(request.cache_key) is served[name].analysis
            and not dependencies_current(
                dependencies=served[name].dependencies,
                parent_signatures=_parent_signatures(
                    request=request,
                    signatures=current_signatures,
                    analyzed_names=analyzed_names,
                ),
            )
        }

    def read(
        self,
        *,
        context: AnalysisCacheContext,
        cache_keys: tuple[str, ...],
        model_names: tuple[str, ...],
        upstream_model_names_by_key: dict[str, tuple[str, ...]],
    ) -> tuple[dict[str, PolyglotAnalysisResult], dict[str, str], dict[str, str]]:
        """Read the analysis cache for keys without a stored analysis; serve the rest."""

        stored: dict[str, StoredModelAnalysis] = self.served
        stored_by_key: dict[str, StoredModelAnalysis] = {
            analysis.cache_key: analysis for analysis in stored.values()
        }
        analyses, signatures, output_signatures = read_model_analyses(
            context=context,
            cache_keys=tuple(key for key in cache_keys if key not in stored_by_key),
            model_names=model_names,
            upstream_model_names_by_key={
                key: names
                for key, names in upstream_model_names_by_key.items()
                if key not in stored_by_key
            },
        )
        for key in cache_keys:
            served: StoredModelAnalysis | None = stored_by_key.get(key)
            if served is not None:
                analyses[key] = served.analysis
                output_signatures[key] = served.output_signature
        return analyses, signatures, output_signatures

    def read_every_model(
        self, *, context: AnalysisCacheContext, requests: tuple[ModelSqlAnalysisRequest, ...]
    ) -> dict[str, PolyglotAnalysisResult]:
        """Read every model's analysis from the cache; record them when the cache held them all."""

        analyzed_names: frozenset[str] = frozenset(
            _name(request.model_input) for request in requests
        )
        cache_keys: tuple[str, ...] = tuple(
            request.cache_key for request in requests if request.cache_key is not None
        )
        analyses, signatures, output_signatures = read_model_analyses(
            context=context,
            cache_keys=cache_keys,
            model_names=tuple(_name(request.model_input) for request in requests),
            upstream_model_names_by_key={
                request.cache_key: referenced_model_names(
                    model_input=request.model_input, available_names=analyzed_names
                )
                for request in requests
                if request.cache_key is not None
            },
        )
        if all(key in analyses for key in cache_keys):
            self._record(
                requests=requests,
                cached=analyses,
                cached_output_signatures=output_signatures,
                written={},
                written_dependencies={},
                previous_signatures=signatures,
                current_signatures={
                    _name(request.model_input): output_signatures[request.cache_key]
                    for request in requests
                    if request.cache_key is not None
                },
            )
        return analyses

    def record_none(self) -> None:
        """Record no analyses, so the next compile analyzes or reads every model from the cache."""

        if self._scope is not None:
            self._scope.reuse.record_analyses(analyses={})

    def publish(
        self,
        *,
        context: AnalysisCacheContext,
        requests: tuple[ModelSqlAnalysisRequest, ...],
        results: tuple[PolyglotAnalysisResult, ...],
        cached: dict[str, PolyglotAnalysisResult],
        cached_output_signatures: dict[str, str],
        invalidated_names: set[str],
        latest_by_model: dict[str, PolyglotAnalysisResult],
        previous_signatures: dict[str, str],
        current_signatures: dict[str, str],
    ) -> None:
        """Write new and invalidated analyses to the cache, then record them for the next run."""

        analyzed_names: frozenset[str] = frozenset(
            _name(request.model_input) for request in requests
        )
        written: dict[str, PolyglotAnalysisResult] = {
            request.cache_key: result
            for request, result in zip(requests, results, strict=True)
            if request.cache_key is not None
            and (request.cache_key not in cached or _name(request.model_input) in invalidated_names)
        }
        written_dependencies: dict[str, dict[str, str]] = {
            key: _dependency_signatures(
                request=request,
                current_signatures=current_signatures,
                analyzed_names=analyzed_names,
            )
            for request in requests
            if (key := request.cache_key) is not None and key in written
        }
        record_compile_metric(
            metric="analysis_reuse_hits",
            value=sum(
                request.cache_key is not None
                and (served := self.served.get(_name(request.model_input))) is not None
                and cached.get(request.cache_key) is served.analysis
                and _name(request.model_input) not in invalidated_names
                for request in requests
            ),
        )
        with record_compile_timing("cache_publication_ms"):
            write_model_analyses(
                context=context,
                analyses_by_key=written,
                latest_analyses_by_model=latest_by_model,
                dependency_signatures_by_key=written_dependencies,
            )
        self._record(
            requests=requests,
            cached=cached,
            cached_output_signatures=cached_output_signatures,
            written=written,
            written_dependencies=written_dependencies,
            previous_signatures=previous_signatures,
            current_signatures=current_signatures,
        )

    def _record(
        self,
        *,
        requests: tuple[ModelSqlAnalysisRequest, ...],
        cached: dict[str, PolyglotAnalysisResult],
        cached_output_signatures: dict[str, str],
        written: dict[str, PolyglotAnalysisResult],
        written_dependencies: dict[str, dict[str, str]],
        previous_signatures: dict[str, str],
        current_signatures: dict[str, str],
    ) -> None:
        if self._scope is None:
            return
        self._scope.reuse.record_analyses(
            analyses=_recorded_analyses(
                scope=self._scope,
                requests=requests,
                cached=cached,
                cached_output_signatures=cached_output_signatures,
                written=written,
                written_dependencies=written_dependencies,
                previous_signatures=previous_signatures,
                current_signatures=current_signatures,
            )
        )


def dependencies_current(
    *, dependencies: dict[str, str], parent_signatures: dict[str, str | None]
) -> bool:
    """Return whether a stored analysis was made from parents with these final signatures."""

    return dependencies == parent_signatures


def _stored_analysis_scope(
    *,
    caching: ModelAnalysisCaching | None,
    requests: tuple[ModelSqlAnalysisRequest, ...],
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    complete_binding_schemas: dict[str, dict[str, str]],
) -> StoredAnalysisScope | None:
    if caching is None or caching.reuse is None:
        return None
    context: str = analysis_reuse_context(
        cache=caching.cache,
        model_names=frozenset(_name(request.model_input) for request in requests),
        column_types_by_table=column_types_by_table,
        column_nullability_by_table=column_nullability_by_table,
        complete_binding_schemas=complete_binding_schemas,
    )
    stored: dict[str, StoredModelAnalysis] = _reusable_stored_analyses(
        reuse=caching.reuse, context=context, requests=requests
    )
    record_compile_metric(metric="analysis_reuse_hits", value=0)
    return StoredAnalysisScope(reuse=caching.reuse, context=context, stored=stored)


def analysis_reuse_context(
    *,
    cache: AnalysisCacheContext,
    model_names: frozenset[str],
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    complete_binding_schemas: dict[str, dict[str, str]],
) -> str:
    """Digest every analysis input shared by all models, including non-model relations."""

    relations: dict[str, list[object]] = {
        name: _relation_inputs(
            name=name,
            column_types_by_table=column_types_by_table,
            column_nullability_by_table=column_nullability_by_table,
            complete_binding_schemas=complete_binding_schemas,
        )
        for name in (
            column_types_by_table.keys()
            | column_nullability_by_table.keys()
            | complete_binding_schemas.keys()
        )
        - model_names
    }
    return hashlib.sha256(
        orjson.dumps(
            {
                "shared_fingerprint": cache.shared_fingerprint,
                "signature_namespace": cache.signature_namespace,
                "relations": relations,
            },
            option=orjson.OPT_SORT_KEYS,
        )
    ).hexdigest()


def _relation_inputs(
    *,
    name: str,
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    complete_binding_schemas: dict[str, dict[str, str]],
) -> list[object]:
    nullability: dict[str, InferredNullability] = column_nullability_by_table.get(name, {})
    return [
        column_types_by_table.get(name),
        {column: value.value for column, value in nullability.items()},
        complete_binding_schemas.get(name),
    ]


def _reusable_stored_analyses(
    *,
    reuse: ModelAnalysisReuse,
    context: str,
    requests: tuple[ModelSqlAnalysisRequest, ...],
) -> dict[str, StoredModelAnalysis]:
    reused_names: frozenset[str] = reuse.reused_model_names()
    stored: dict[str, StoredModelAnalysis] = reuse.stored_analyses()
    key_counts: Counter[str | None] = Counter(request.cache_key for request in requests)
    reusable: dict[str, StoredModelAnalysis] = {}
    for request in requests:
        name: str = _name(request.model_input)
        analysis: StoredModelAnalysis | None = stored.get(name)
        if (
            analysis is not None
            and analysis.context == context
            and name in reused_names
            and request.cache_key is not None
            and analysis.cache_key == request.cache_key
            and key_counts[request.cache_key] == 1
        ):
            reusable[name] = analysis
    return reusable


def _parent_signatures(
    *,
    request: ModelSqlAnalysisRequest,
    signatures: dict[str, str],
    analyzed_names: frozenset[str],
) -> dict[str, str | None]:
    return {
        upstream_name: signatures.get(upstream_name)
        for upstream_name in referenced_model_names(
            model_input=request.model_input, available_names=analyzed_names
        )
    }


def _dependency_signatures(
    *,
    request: ModelSqlAnalysisRequest,
    current_signatures: dict[str, str],
    analyzed_names: frozenset[str],
) -> dict[str, str]:
    return {
        upstream_name: current_signatures[upstream_name]
        for upstream_name in referenced_model_names(
            model_input=request.model_input, available_names=analyzed_names
        )
        if upstream_name in current_signatures
    }


def _recorded_analyses(
    *,
    scope: StoredAnalysisScope,
    requests: tuple[ModelSqlAnalysisRequest, ...],
    cached: dict[str, PolyglotAnalysisResult],
    cached_output_signatures: dict[str, str],
    written: dict[str, PolyglotAnalysisResult],
    written_dependencies: dict[str, dict[str, str]],
    previous_signatures: dict[str, str],
    current_signatures: dict[str, str],
) -> dict[str, StoredModelAnalysis | None]:
    analyzed_names: frozenset[str] = frozenset(_name(request.model_input) for request in requests)
    recorded: dict[str, StoredModelAnalysis | None] = {}
    for request in requests:
        name: str = _name(request.model_input)
        key: str | None = request.cache_key
        written_analysis: PolyglotAnalysisResult | None = None if key is None else written.get(key)
        cached_analysis: PolyglotAnalysisResult | None = None if key is None else cached.get(key)
        previous: StoredModelAnalysis | None = scope.stored.get(name)
        upstream: tuple[str, ...] = referenced_model_names(
            model_input=request.model_input, available_names=analyzed_names
        )
        parents: dict[str, str | None] = _parent_signatures(
            request=request, signatures=current_signatures, analyzed_names=analyzed_names
        )
        if key is None or (written_analysis is None and cached_analysis is None):
            recorded[name] = None
        elif written_analysis is not None:
            recorded[name] = StoredModelAnalysis(
                context=scope.context,
                cache_key=key,
                analysis=written_analysis,
                output_signature=model_analysis_output_signature(written_analysis),
                dependencies=written_dependencies.get(key, {}),
                signature=current_signatures.get(name),
            )
        elif (
            previous is not None
            and previous.cache_key == key
            and previous.analysis is cached_analysis
            and previous.signature == current_signatures.get(name)
            and dependencies_current(dependencies=previous.dependencies, parent_signatures=parents)
        ):
            recorded[name] = previous
        elif cached_analysis is not None and all(
            upstream_name in previous_signatures
            and previous_signatures[upstream_name] == parents[upstream_name]
            for upstream_name in upstream
        ):
            recorded[name] = StoredModelAnalysis(
                context=scope.context,
                cache_key=key,
                analysis=cached_analysis,
                output_signature=cached_output_signatures.get(key)
                or model_analysis_output_signature(cached_analysis),
                dependencies={
                    upstream_name: previous_signatures[upstream_name] for upstream_name in upstream
                },
                signature=current_signatures.get(name),
            )
        else:
            recorded[name] = None
    return recorded


def _name(model_input: CompileModelInput) -> str:
    return model_input.model_file.file_path.stem
