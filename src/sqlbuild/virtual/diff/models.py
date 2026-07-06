"""Virtual diff domain models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)


@dataclass(frozen=True)
class VirtualDiffState:
    """Bound refs, semantics, and physical relations for both diffed VDEs."""

    from_environment: VirtualEnvironmentRecord | None
    to_environment: VirtualEnvironmentRecord | None
    from_refs: tuple[VirtualEnvironmentModelRefRecord, ...]
    to_refs: tuple[VirtualEnvironmentModelRefRecord, ...]
    from_semantics: VirtualPlanSemantics
    to_semantics: VirtualPlanSemantics
    from_relations: dict[str, PhysicalRelationRecord]
    to_relations: dict[str, PhysicalRelationRecord]
