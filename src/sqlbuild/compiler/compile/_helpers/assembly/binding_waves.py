"""Analyze open model inputs after their producers have supplied closed shapes."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.classes.binding_dataflow import BindingDataflow
from sqlbuild.compiler.compile.models import CompileModelInput, PolyglotAnalysisResult
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysis as _ModelSqlAnalysis,
)
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysisRequest as _ModelSqlAnalysisRequest,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.references.types import SqlReferenceKind

_DATAFLOW_WORKERS: int = 4
_DATAFLOW_BATCH_MIN: int = 8
_DATAFLOW_BATCH_LIMIT: int = 64


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
    """Analyze one topological level at a time, the reference for dataflow scheduling."""

    return BindingDataflow(
        requests=requests,
        names=names,
        cached=cached,
        previous_signatures=previous_signatures,
        shapes=shapes,
        types=types,
        nullability=nullability,
        profile=profile,
        analyze=analyze,
        complete=complete,
    ).analyze_waves()


def analyze_binding_dataflow(
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
    """Analyze each model once its producers are final; replay waves after any error."""

    create: Callable[[], BindingDataflow] = partial(
        BindingDataflow,
        requests=requests,
        names=names,
        cached=cached,
        previous_signatures=previous_signatures,
        shapes=shapes,
        types=types,
        nullability=nullability,
        profile=profile,
        analyze=analyze,
        complete=complete,
    )
    result: tuple[tuple[_ModelSqlAnalysis, ...], dict[str, PolyglotAnalysisResult]] | None = (
        create().analyze_dataflow(
            workers=_DATAFLOW_WORKERS,
            batch_min=_DATAFLOW_BATCH_MIN,
            batch_limit=_DATAFLOW_BATCH_LIMIT,
        )
    )
    return result if result is not None else create().analyze_waves()


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
