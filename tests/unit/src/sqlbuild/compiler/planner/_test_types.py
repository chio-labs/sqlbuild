from dataclasses import dataclass

from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, RelationReuseKind


@dataclass(frozen=True)
class RelationReuseValidationTestCase:
    description: str
    materialization_type: MaterializationType
    action: PlanAction
    reuse_kind: RelationReuseKind
    incremental_strategy: str | None
    expected_error_fragment: str


@dataclass(frozen=True)
class DurationParseTestCase:
    description: str
    value: str
    expected_years: int
    expected_months: int
    expected_days: int
    expected_hours: int
    expected_minutes: int
    expected_seconds: int
    expected_has_calendar_component: bool
    expected_fixed_seconds: int


@dataclass(frozen=True)
class DurationParseNoneTestCase:
    description: str
    value: str
    expected_is_none: bool


@dataclass(frozen=True)
class DurationShiftTestCase:
    description: str
    value: str
    moment: str
    expected_added: str
    expected_subtracted: str
