"""Virtual planner models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.planner.types import PlanReason


@dataclass(frozen=True)
class VirtualPlanSemantics:
    """Derived virtual planning semantics for one VDE."""

    expected_local_hashes: dict[str, str] = field(default_factory=dict)
    expected_version_hashes: dict[str, str] = field(default_factory=dict)
    bound_version_hashes: dict[str, str] = field(default_factory=dict)
    bound_local_hashes: dict[str, str] = field(default_factory=dict)
    stale_model_names: tuple[str, ...] = ()
    default_selection: tuple[str, ...] = ()
    stale_root_reasons: dict[str, PlanReason] = field(default_factory=dict)
    stale_root_causes: dict[str, str] = field(default_factory=dict)
