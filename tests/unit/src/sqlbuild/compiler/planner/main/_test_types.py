from dataclasses import dataclass

from sqlbuild.compiler.planner.types import StandardScopePruning


@dataclass(frozen=True)
class StandardSourceFreshnessPlanOutputTestCase:
    description: str
    standard_scope_pruning: StandardScopePruning
    expected_has_source_freshness: bool


@dataclass(frozen=True)
class HookFunctionPlanOutputTestCase:
    description: str
    expected_hook_names: tuple[str, ...]


@dataclass(frozen=True)
class ExternalBlockedPlanOutputTestCase:
    description: str
    expected_model_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardReuseFromTargetPlanOutputTestCase:
    description: str
    expected_reuse_from_target_name: str
    expected_model_names: tuple[str, ...]
    expected_reuse_eligible_names: tuple[str, ...]
    expected_decisions: dict[str, str]
    expected_actions: dict[str, str]


@dataclass(frozen=True)
class StandardReuseFullRefreshBypassTestCase:
    description: str
    expected_reuse_from_target_metadata_present: bool
    expected_reuse_decision_metadata_present: bool


@dataclass(frozen=True)
class StandardReuseFromSourceDeferralConflictTestCase:
    description: str
    defer_sources_to: str | None
    target_defer_sources_to: str | None
    expected_error_fragment: str
