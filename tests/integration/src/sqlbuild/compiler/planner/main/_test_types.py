from dataclasses import dataclass, field

from sqlbuild.compiler.planner.types import (
    PlanAction,
    PlanReason,
    WarningSeverity,
)


@dataclass(frozen=True)
class BuildExecutionPlanTestCase:
    description: str
    setup_sql: tuple[str, ...]
    model_targets: dict[str, str]
    model_configs: dict[str, dict[str, object]]
    model_queries: dict[str, str]
    full_refresh: bool
    expected_action: dict[str, PlanAction]
    expected_reason: dict[str, PlanReason]
    expected_ddl_fragments: dict[str, str] = field(default_factory=dict)
    expected_warning_severity: WarningSeverity | None = None
    expected_warning_count: int = 0
