"""Virtual planner models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.planner.models import CursorOverrides, RunDespiteUnchangedPlanningResult
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver


@dataclass(frozen=True)
class VirtualPlanOptions:
    """Selection, deferral, and cursor options for one virtual planning run."""

    selected_target: str | None = None
    no_sql_validation: bool = False
    defer_sources_to: str | None = None
    source_deferral_enabled: bool = True
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cursor_overrides: CursorOverrides | None = None
    full_refresh: bool = False
    virtual_environment_name: str | None = None
    include_stale_upstreams: bool = False
    changes_only: bool = False
    auto_load_sources: bool = False
    reload_sources: bool = False
    include_python: bool = True
    cli_vars: dict[str, object] | None = None
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None


@dataclass(frozen=True)
class ExpectedIdentityFacts:
    """Expected identity hashes and source-freshness coverage from the graph."""

    local_hashes: dict[str, str] = field(default_factory=dict)
    metadata_jsons: dict[str, str] = field(default_factory=dict)
    seed_version_hashes: dict[str, str] = field(default_factory=dict)
    seed_identity_metadata_jsons: dict[str, str] = field(default_factory=dict)
    version_hashes: dict[str, str] = field(default_factory=dict)
    source_version_hashes: dict[str, str] = field(default_factory=dict)
    source_freshness_observed_source_names: tuple[str, ...] = ()
    source_freshness_incomplete_source_names: tuple[str, ...] = ()
    source_freshness_incomplete_model_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoundIdentityFacts:
    """Bound identity hashes decoded from persisted virtual state."""

    version_hashes: dict[str, str] = field(default_factory=dict)
    seed_version_hashes: dict[str, str] = field(default_factory=dict)
    local_hashes: dict[str, str] = field(default_factory=dict)
    previous_query_sqls: dict[str, str] = field(default_factory=dict)
    metadata_jsons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StalenessFacts:
    """Stale models/seeds with their root reasons and causes."""

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
    source_freshness_unchanged_source_names: tuple[str, ...] = ()
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
