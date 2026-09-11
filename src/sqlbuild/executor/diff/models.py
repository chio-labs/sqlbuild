"""Diff executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.contract.models import RowDiffResult, RowDiffSampleRow, SchemaDiffResult


@dataclass(frozen=True)
class RowDiffSamplingOverride:
    """Invocation-level sampling values that override compiled model configuration."""

    row_limit: int | None = None
    seed: int | None = None
    exhaustive: bool = False


@dataclass(frozen=True)
class DiffExecutionOptions:
    """Row-diff mode, diagnostic, and invocation override options."""

    schema_only: bool
    bounded: str | None = None
    collect_samples: bool = False
    max_column_examples: int = 20
    max_row_only_examples: int = 20
    max_models: int | None = None
    max_columns: int | None = None
    sampling_override: RowDiffSamplingOverride = field(default_factory=RowDiffSamplingOverride)


@dataclass(frozen=True)
class ModelDiffResult:
    """Diff result for one model across two targets."""

    name: str
    left_relation: str
    right_relation: str
    schema_result: SchemaDiffResult
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    row_result: RowDiffResult | None = None
    unequal_row_samples: tuple[RowDiffSampleRow, ...] = field(default_factory=tuple)
    left_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = field(default_factory=tuple)
    right_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = field(
        default_factory=tuple
    )
    bounded_fallback: bool = False
    excluded_columns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiffExecutionResult:
    """Complete diff command result."""

    model_results: tuple[ModelDiffResult, ...] = field(default_factory=tuple)
