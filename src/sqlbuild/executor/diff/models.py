"""Diff executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import RowDiffResult, SchemaDiffResult


@dataclass(frozen=True)
class ModelDiffResult:
    """Diff result for one model across two environments."""

    name: str
    left_relation: str
    right_relation: str
    schema_result: SchemaDiffResult
    row_result: RowDiffResult | None = None
    bounded_fallback: bool = False


@dataclass(frozen=True)
class DiffExecutionResult:
    """Complete diff command result."""

    model_results: tuple[ModelDiffResult, ...] = field(default_factory=tuple)
