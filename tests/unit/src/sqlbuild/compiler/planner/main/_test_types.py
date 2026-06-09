from dataclasses import dataclass


@dataclass(frozen=True)
class StandardSourceFreshnessPlanOutputTestCase:
    description: str
    changes_only: bool
    expected_has_source_freshness: bool


@dataclass(frozen=True)
class HookFunctionPlanOutputTestCase:
    description: str
    expected_hook_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardReuseFromTargetPlanOutputTestCase:
    description: str
    expected_reuse_from_target_name: str
    expected_model_names: tuple[str, ...]
    expected_reuse_candidate_names: tuple[str, ...]
    expected_decisions: dict[str, str]


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
