from dataclasses import dataclass
from datetime import datetime

from sqlbuild.compiler.planner.models import (
    CursorBounds,
    SelectionStalenessGraph,
    SelectionStalenessWarning,
)
from sqlbuild.spec.contracts.models import FutureCursorsConfig


@dataclass(frozen=True)
class CloneBoundaryTestCase:
    description: str
    upstream: dict[str, tuple[str, ...]]
    selected: frozenset[str]
    clonable_nodes: frozenset[str]
    view_nodes: frozenset[str]
    expected_boundary_nodes: frozenset[str]
    expected_view_chain_nodes: frozenset[str]


@dataclass(frozen=True)
class DirectSourceFreshnessPlanOutputTestCase:
    description: str
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
class DirectInputBaselineTestCase:
    description: str
    models_by_name: dict[str, str]
    origin_model_names: tuple[str, ...]
    selected_model_name: str
    expected_baseline_names: tuple[str, ...]
    unexpected_baseline_names: tuple[str, ...]


@dataclass(frozen=True)
class LocalNodePlanningTestCase:
    description: str
    fingerprint_exists: bool
    relation_exists: bool
    full_refresh: bool
    local_hash: str | None
    previous_hash: str | None
    expected_action: str
    expected_reason: str


@dataclass(frozen=True)
class SelectorExpansionTestCase:
    description: str
    raw: str
    expected_core: str
    expected_upstream: bool
    expected_downstream: bool


@dataclass(frozen=True)
class SelectorExpansionErrorTestCase:
    description: str
    raw: str
    expected_error_type: type[Exception]


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


@dataclass(frozen=True)
class InclusiveCursorEndTestCase:
    description: str
    end: str
    cursor_type: str | None
    cursor_grain: str | None
    expected_end: str


@dataclass(frozen=True)
class AdvanceCursorEndTestCase:
    description: str
    value: str
    cursor_type: str | None
    cursor_grain: str | None
    expected_end: str


@dataclass(frozen=True)
class CursorEndRoundTripTestCase:
    description: str
    inclusive_value: str
    cursor_type: str | None
    cursor_grain: str | None
    expected_round_trip: str


@dataclass(frozen=True)
class CursorBoundDisplayTestCase:
    description: str
    value: str
    cursor_type: str | None
    cursor_grain: str | None
    expected_display: str


@dataclass(frozen=True)
class EffectiveMicrobatchBatchSizeTestCase:
    description: str
    batch_size: str
    effective_grain: str
    expected_batch_size: str


@dataclass(frozen=True)
class FutureCursorSafetyTestCase:
    description: str
    bounds: CursorBounds
    config: FutureCursorsConfig
    invocation_time: datetime
    cursor_grain: str
    has_complete_override: bool
    expected_start: str
    expected_end: str
    expected_has_safety: bool
    expected_error_fragment: str | None = None
