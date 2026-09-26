"""Analyze open model inputs after their producers have supplied closed shapes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from graphlib import CycleError, TopologicalSorter

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.cache import model_analysis_output_signature
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    binding_relation_names,
    inferred_binding_shape,
)
from sqlbuild.compiler.compile.models import CompileModelInput, PolyglotAnalysisResult
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysis as _ModelSqlAnalysis,
)
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysisRequest as _ModelSqlAnalysisRequest,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.references.types import SqlReferenceKind


def analyze_binding_waves(
    *,
    requests: tuple[_ModelSqlAnalysisRequest, ...],
    names: tuple[str, ...],
    cached: dict[str, PolyglotAnalysisResult],
    previous_signatures: dict[str, str],
    shapes: dict[str, dict[str, str]],
    types: dict[str, dict[str, str]],
    nullability: dict[str, dict[str, InferredNullability]],
    profile: ExpressionInferenceProfile,
    analyze: Callable[..., tuple[_ModelSqlAnalysis, ...]],
    complete: Callable[..., tuple[_ModelSqlAnalysis, ...]],
) -> tuple[tuple[_ModelSqlAnalysis, ...], dict[str, PolyglotAnalysisResult]]:
    by_name: dict[str, _ModelSqlAnalysisRequest] = dict(zip(names, requests, strict=True))
    available_names: frozenset[str] = frozenset(by_name)
    dependencies: dict[str, tuple[str, ...]] = {}
    for name, request in by_name.items():
        dependencies[name] = referenced_model_names(
            model_input=request.model_input, available_names=available_names
        )
    sorter: TopologicalSorter[str] = TopologicalSorter(dependencies)
    try:
        sorter.prepare()
    except CycleError:
        return complete(
            requests=requests,
            analyses=analyze(
                requests=requests,
                cached_analyses=cached,
                column_types_by_table=types,
                column_nullability_by_table=nullability,
            ),
            complete_binding_schemas=shapes,
        ), cached
    complete_shapes: dict[str, dict[str, str]] = dict(shapes)
    available_types: dict[str, dict[str, str]] = dict(types)
    available_nullability: dict[str, dict[str, InferredNullability]] = dict(nullability)
    reusable: dict[str, PolyglotAnalysisResult] = dict(cached)
    changed: set[str] = set()
    results: dict[str, _ModelSqlAnalysis] = {}
    while sorter.is_active():
        ready: tuple[str, ...] = tuple(sorter.get_ready())
        wave: list[_ModelSqlAnalysisRequest] = []
        for name in ready:
            request: _ModelSqlAnalysisRequest = by_name[name]
            if any(parent in changed for parent in dependencies[name]):
                changed.add(name)
                if request.cache_key is not None:
                    reusable.pop(request.cache_key, None)
            bindings: dict[str, dict[str, str]] | None = (
                None
                if request.binding_schema is None
                else {
                    relation: complete_shapes.get(relation, {})
                    for relation in binding_relation_names(request.model_input.references)
                }
            )
            wave.append(replace(request, binding_schema=bindings))
        wave_requests: tuple[_ModelSqlAnalysisRequest, ...] = tuple(wave)
        wave_names: set[str] = set(ready)
        for request in wave_requests:
            wave_names.update(binding_relation_names(request.model_input.references))
        analyses: tuple[_ModelSqlAnalysis, ...] = complete(
            requests=wave_requests,
            analyses=analyze(
                requests=wave_requests,
                cached_analyses=reusable,
                column_types_by_table=available_types,
                column_nullability_by_table=available_nullability,
            ),
            complete_binding_schemas={
                name: complete_shapes[name] for name in wave_names if name in complete_shapes
            },
        )
        for name, request, result in zip(ready, wave_requests, analyses, strict=True):
            results[name] = result
            analysis: PolyglotAnalysisResult = result.polyglot_analysis
            if model_analysis_output_signature(analysis) != previous_signatures.get(name):
                changed.add(name)
            required: frozenset[str] = binding_relation_names(request.model_input.references)
            if analysis.columns and (not analysis.has_star or required <= complete_shapes.keys()):
                shape: dict[str, str] = inferred_binding_shape(
                    sql=result.cleaned_sql or request.query_sql,
                    columns={column.name: column.type or "UNKNOWN" for column in analysis.columns},
                    inputs={table: complete_shapes.get(table, {}) for table in required},
                    profile=profile,
                )
                complete_shapes.setdefault(name, shape)
                available_types.setdefault(name, shape)
                available_nullability.setdefault(
                    name, dict.fromkeys(shape, InferredNullability.UNKNOWN)
                )
        sorter.done(*ready)
    return tuple(results[name] for name in names), reusable


def downstream_model_names(
    *, model_inputs: tuple[CompileModelInput, ...], changed_names: set[str]
) -> set[str]:
    downstream_by_name: dict[str, set[str]] = {}
    for model_input in model_inputs:
        for reference in model_input.references:
            if reference.ref_kind == SqlReferenceKind.REF:
                downstream_by_name.setdefault(reference.ref_name, set()).add(
                    model_input.model_file.file_path.stem
                )
    downstream_names: set[str] = set()
    pending: list[str] = list(changed_names)
    while pending:
        for downstream_name in downstream_by_name.get(pending.pop(), set()):
            if downstream_name not in downstream_names and downstream_name not in changed_names:
                downstream_names.add(downstream_name)
                pending.append(downstream_name)
    return downstream_names


def referenced_model_names(
    *, model_input: CompileModelInput, available_names: frozenset[str] | None = None
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                reference.ref_name
                for reference in model_input.references
                if reference.ref_kind == SqlReferenceKind.REF
                and (available_names is None or reference.ref_name in available_names)
            }
        )
    )
