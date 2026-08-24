"""Test types for concurrent build execution tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.scheduling.types import ExecutionStatus


@dataclass(frozen=True)
class ConcurrentBuildTestCase:
    """Test case for concurrent build execution with file-based DuckDB."""

    description: str
    project_files: dict[str, str]
    max_concurrency: int
    expected_status: BuildStatus
    expected_success_count: int = 0
    expected_failure_count: int = 0
    expected_skipped_count: int = 0
    expected_model_statuses: tuple[tuple[str, ExecutionStatus], ...] = field(default_factory=tuple)
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    expected_missing_relations: tuple[str, ...] = field(default_factory=tuple)
    setup_sql: tuple[str, ...] = field(default_factory=tuple)
    run_audits: bool = True
    fail_fast: bool = False
    use_provider_session: bool = False
    expected_marker_entries: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OrderingInvariantTestCase:
    """Test case for verifying dependency ordering under concurrency."""

    description: str
    project_files: dict[str, str]
    max_concurrency: int
    expected_upstream_model_deps: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class MicrobatchSchedulerTestCase:
    """Expected global-budget behavior for concurrent microbatch models."""

    description: str
    expected_status: BuildStatus
    expected_max_active_batches: int
    expected_max_active_models: int
    expected_row_count: int
    expected_completion_count: int
    expected_unattributed_batches: int
