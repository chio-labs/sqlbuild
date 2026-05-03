from dataclasses import dataclass, field

from sqlbuild.executor.shared.types import ExecutionPhase


@dataclass(frozen=True)
class ViewSuccessTestCase:
    """Test case where view execution succeeds."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    expected_row_count: int
    expected_audit_count: int = 0
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    extra_audits: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    query_change_tracking: bool = True
    expected_warning_fragment: str | None = None


@dataclass(frozen=True)
class ViewFailureTestCase:
    """Test case where view execution fails at a specific phase."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    expected_failed_phase: ExecutionPhase
    expected_audit_count: int = 0
    expected_error_fragment: str | None = None
    expected_promoted_relation: str | None = None
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    extra_audits: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
