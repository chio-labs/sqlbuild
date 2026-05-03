from dataclasses import dataclass, field

from sqlbuild.executor.shared.types import (
    ExecutionPhase,
    TablePromotionMode,
)


@dataclass(frozen=True)
class TableSuccessTestCase:
    """Test case where execution succeeds and target is populated."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    promotion_mode: TablePromotionMode
    expected_row_count: int
    expected_audit_count: int = 0
    type_enforcement: bool = False
    declared_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    extra_audits: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    fingerprint_schema: str | None = None
    expected_column_names: tuple[str, ...] = field(default_factory=tuple)
    expected_column_types: tuple[str, ...] = field(default_factory=tuple)
    expected_warning_fragment: str | None = None


@dataclass(frozen=True)
class TableFailureTestCase:
    """Test case where execution fails at a specific phase."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    promotion_mode: TablePromotionMode
    expected_failed_phase: ExecutionPhase
    expected_audit_count: int = 0
    expected_error_fragment: str | None = None
    expected_staging_relation: str | None = None
    expected_promoted_relation: str | None = None
    expected_row_count: int | None = None
    type_enforcement: bool = False
    declared_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    extra_audits: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
