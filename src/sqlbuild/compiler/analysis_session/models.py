"""Inputs handed to the native model analysis session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.types import QueryColumnsMode
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompileModelInput,
    CompileSqlReference,
    InferredColumn,
    ModelSqlAnalysis,
)
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


@dataclass(frozen=True, slots=True)
class NativeModelAnalyses:
    """Each model's native analysis by name, and the finished session that produced them."""

    analyses: dict[str, ModelSqlAnalysis]
    session: Any | None


@dataclass(frozen=True, slots=True)
class NativePivotTables:
    """The relation facts Python's dynamic pivot proofs read, for proofs outside a session."""

    dialect: str | None
    column_types_by_table: dict[str, dict[str, str]]
    authoritative_column_types_by_table: dict[str, dict[str, str]]
    column_nullability_by_table: dict[str, dict[str, InferredNullability]]
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]]


@dataclass(frozen=True, slots=True)
class NativeColumnQuery:
    """One query outside the session whose output columns Python's analysis inferred."""

    sql: str
    mode: QueryColumnsMode
    placeholders: dict[str, str] | None = None
    references: tuple[CompileSqlReference, ...] = ()
    recover_cte_facts: bool = True


@dataclass(frozen=True, slots=True)
class NativeQueryColumns:
    """One query's analysis: whether it succeeded, its columns and whether it projects a star."""

    succeeded: bool
    columns: tuple[InferredColumn, ...] | None
    has_star: bool
