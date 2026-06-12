"""Virtual planner models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.planner.models import RunDespiteUnchangedPlanningResult
from sqlbuild.compiler.planner.types import PlanReason


@dataclass(frozen=True)
class VirtualPlanSemantics:
    """Derived virtual planning semantics for one VDE."""

    expected_local_hashes: dict[str, str] = field(default_factory=dict)
    expected_metadata_jsons: dict[str, str] = field(default_factory=dict)
    expected_version_hashes: dict[str, str] = field(default_factory=dict)
    expected_seed_version_hashes: dict[str, str] = field(default_factory=dict)
    seed_identity_metadata_jsons: dict[str, str] = field(default_factory=dict)
    bound_version_hashes: dict[str, str] = field(default_factory=dict)
    bound_seed_version_hashes: dict[str, str] = field(default_factory=dict)
    bound_local_hashes: dict[str, str] = field(default_factory=dict)
    bound_previous_query_sqls: dict[str, str] = field(default_factory=dict)
    bound_metadata_jsons: dict[str, str] = field(default_factory=dict)
    source_freshness_observed_source_names: tuple[str, ...] = ()
    source_freshness_incomplete_source_names: tuple[str, ...] = ()
    source_freshness_incomplete_model_names: tuple[str, ...] = ()
    stale_seed_names: tuple[str, ...] = ()
    seed_plan_reasons: dict[str, PlanReason] = field(default_factory=dict)
    stale_model_names: tuple[str, ...] = ()
    default_selection: tuple[str, ...] = ()
    run_despite_unchanged: RunDespiteUnchangedPlanningResult = field(
        default_factory=RunDespiteUnchangedPlanningResult
    )
    stale_root_reasons: dict[str, PlanReason] = field(default_factory=dict)
    stale_root_causes: dict[str, str] = field(default_factory=dict)
    stale_root_cause_reasons: dict[str, PlanReason] = field(default_factory=dict)
