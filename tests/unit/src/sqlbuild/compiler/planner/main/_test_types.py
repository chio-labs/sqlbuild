from dataclasses import dataclass

from sqlbuild.compiler.planner.models import (
    SelectionStalenessGraph,
    SelectionStalenessWarning,
)
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
class StandardDependencyBaselinePlanOutputTestCase:
    description: str
    selected_model_name: str
    expected_model_names: tuple[str, ...]
    expected_dependency_baseline_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardDirectInputBaselineTestCase:
    description: str
    models_by_name: dict[str, str]
    origin_model_names: tuple[str, ...]
    selected_model_name: str
    expected_baseline_names: tuple[str, ...]
    unexpected_baseline_names: tuple[str, ...]


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


@dataclass(frozen=True)
class StandardSelectionAwareStalenessTestCase:
    description: str
    previous_sql_by_model_name: dict[str, str]
    current_sql_by_model_name: dict[str, str]
    select: tuple[str, ...]
    expected_model_names: tuple[str, ...]
    expected_warning_fragments: tuple[str, ...]
    full_refresh: bool = False
    model_configs: dict[str, dict[str, object]] | None = None
    expected_current_version_hash_model_names: tuple[str, ...] = ()
    expected_non_current_version_hash_model_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectionStalenessClassifierTestCase:
    description: str
    graph: SelectionStalenessGraph
    expected_warnings: tuple[SelectionStalenessWarning, ...]


@dataclass(frozen=True)
class SqlbuildModelSelectorNamesTestCase:
    description: str
    term: str
    expected_model_names: tuple[str, ...]
    expected_translation: str | None
