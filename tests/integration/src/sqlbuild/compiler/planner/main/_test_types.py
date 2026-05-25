from dataclasses import dataclass, field

from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    PlanAction,
    PlanReason,
    WarningSeverity,
)


@dataclass(frozen=True)
class FormatPlanIntegrationTestCase:
    description: str
    setup_sql: tuple[str, ...]
    model_targets: dict[str, str]
    model_configs: dict[str, dict[str, object]]
    model_queries: dict[str, str]
    full_refresh: bool
    expected_format_fragments: tuple[str, ...]
    unexpected_format_fragments: tuple[str, ...] = ()
    model_deps: dict[str, tuple[str, ...]] = field(default_factory=dict)
    seed_targets: dict[str, str] = field(default_factory=dict)
    effective_connection: dict[str, object] = field(default_factory=dict)


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
    expected_warning_fragment: str | None = None
    seed_targets: dict[str, str] = field(default_factory=dict)
    function_targets: dict[str, str] = field(default_factory=dict)
    function_bodies: dict[str, str] = field(default_factory=dict)
    previous_function_bodies: dict[str, str] = field(default_factory=dict)
    function_query_change_backfills: dict[str, str] = field(default_factory=dict)
    function_languages: dict[str, FunctionLanguage] = field(default_factory=dict)
    function_deps: dict[str, tuple[str, ...]] = field(default_factory=dict)
    select: tuple[str, ...] = ()
    expected_seed_names: tuple[str, ...] = ()
    expected_model_count: int | None = None
    effective_connection: dict[str, object] = field(default_factory=dict)
    model_deps: dict[str, tuple[str, ...]] = field(default_factory=dict)
    expected_cascade_action: dict[str, BackfillAction] = field(default_factory=dict)
    expected_cascade_duration: dict[str, str | None] = field(default_factory=dict)
    expected_cascade_root_cause: dict[str, str] = field(default_factory=dict)
    expected_progress_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceCursorInputPlanErrorTestCase:
    description: str
    setup_sql: tuple[str, ...]
    model_name: str
    source_name: str
    source_schema: str
    source_table: str
    cursor_column: str
    cursor_input_column: str
    expected_error_fragment: str
