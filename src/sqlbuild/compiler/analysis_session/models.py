"""Inputs handed to the native model analysis session."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import AnalysisCacheContext, CompileModelInput
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


@dataclass(frozen=True)
class NativeModelAnalysisRequest:
    """The Python model analysis's arguments plus the facts dynamic pivot proofs need."""

    known_functions: tuple[str, ...]
    known_types: tuple[str, ...]
    model_inputs: tuple[CompileModelInput, ...]
    column_nullability_by_table: dict[str, dict[str, InferredNullability]]
    column_types_by_table: dict[str, dict[str, str]]
    inference_profile: ExpressionInferenceProfile
    allow_compact_analysis: bool
    rich_type_inference: bool
    analysis_cache: AnalysisCacheContext | None
    complete_binding_schemas: dict[str, dict[str, str]]
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]]
