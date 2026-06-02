"""Diff executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import RowDiffResult, RowDiffSampleRow, SchemaDiffResult


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
