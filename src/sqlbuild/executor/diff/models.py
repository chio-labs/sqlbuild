"""Diff executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.contract.models import (
    RelationInfo,
    RowDiffResult,
    RowDiffSampleRow,
    RowDiffTolerances,
    SchemaDiffResult,
)
from sqlbuild.executor.diff.constants import DIFF_INPUT_KIND_MODEL


@dataclass(frozen=True)
class QueryDiffArtifact:
    """One physical query result and its immutable ownership identity."""

    side: str
    run_id: str
    database: str | None
    schema: str
    name: str
    relation: str
    node_name: str


@dataclass(frozen=True)
class QueryDiffArtifactInspection:
    """Expired owned artifacts and reserved-name relations requiring manual review."""

    expired: tuple[QueryDiffArtifact, ...] = ()
    untracked: tuple[RelationInfo, ...] = ()


@dataclass(frozen=True)
class QueryDiffArtifactCleanupResult:
    """Reconciliation outcome for one target schema."""

    cleaned: tuple[str, ...] = ()
    untracked: tuple[RelationInfo, ...] = ()


@dataclass(frozen=True)
class RowDiffSamplingOverride:
    """Invocation-level sampling values that override compiled model configuration."""

    row_limit: int | None = None
    seed: int | None = None
    exhaustive: bool = False


@dataclass(frozen=True)
class FullDiffSizeLimits:
    """Per-side row limits guarding a default full comparison; ``None`` means unlimited."""

    left_target: str
    right_target: str
    left_max_rows: int | None
    right_max_rows: int | None


@dataclass(frozen=True)
class FullDiffSideSize:
    """Metadata row count for one side of a guarded full comparison."""

    target: str
    relation: str
    row_count: int | None
    max_rows: int | None
    detail: str | None = None

    @property
    def exceeds_limit(self) -> bool:
        """Return whether this side blocks the comparison; unknown sizes count as over."""

        return self.max_rows is not None and (
            self.row_count is None or self.row_count > self.max_rows
        )


@dataclass(frozen=True)
class FullDiffModelSize:
    """Both sides' metadata row counts for one model in a guarded full comparison."""

    name: str
    left: FullDiffSideSize
    right: FullDiffSideSize
    has_cursor: bool

    @property
    def exceeds_limit(self) -> bool:
        """Return whether either side blocks the comparison."""

        return self.left.exceeds_limit or self.right.exceeds_limit


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
    unique_key_override: tuple[str, ...] = ()
    unkeyed: bool = False
    excluded_columns_override: tuple[str, ...] = ()
    tolerance_overrides: RowDiffTolerances | None = None
    comparison_name: str | None = None
    full_size_limits: FullDiffSizeLimits | None = None


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
    input_kind: str = DIFF_INPUT_KIND_MODEL
    unkeyed: bool = False


@dataclass(frozen=True)
class DiffExecutionResult:
    """Complete diff command result."""

    model_results: tuple[ModelDiffResult, ...] = field(default_factory=tuple)
