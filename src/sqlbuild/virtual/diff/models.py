"""Virtual diff domain models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)


@dataclass(frozen=True)
class VirtualDiffOptions:
    """Selection, comparison, and sampling options for one virtual diff run."""

    no_sql_validation: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    schema_only: bool = False
    bounded: str | None = None
    collect_samples: bool = False
    max_column_examples: int = 20
    max_row_only_examples: int = 20
    allow_partial_diff: bool = False
    cli_vars: dict[str, object] | None = None
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None


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
