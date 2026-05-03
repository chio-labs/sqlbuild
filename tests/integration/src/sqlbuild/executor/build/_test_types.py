from dataclasses import dataclass, field

from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class BuildExecutionTestCase:
    """Test case for build plan execution with a fake project."""

    description: str
    project_files: dict[str, str]
    expected_status: BuildStatus
    expected_success_count: int = 0
    expected_failure_count: int = 0
    expected_skipped_count: int = 0
    setup_sql: tuple[str, ...] = field(default_factory=tuple)
    run_audits: bool = True
    run_tests: bool = True
    fail_fast: bool = False
    expected_model_statuses: tuple[tuple[str, ExecutionStatus], ...] = field(default_factory=tuple)
    expected_model_audit_count: int = 0
    expected_source_audit_count: int = 0
    expected_end_audit_count: int = 0
    expected_test_count: int = 0
    expected_warning_count: int = 0
    query_change_tracking: bool = True
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    expected_missing_relations: tuple[str, ...] = field(default_factory=tuple)
