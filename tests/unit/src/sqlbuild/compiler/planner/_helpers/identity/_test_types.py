"""Test case types for planner identity helper tests."""

from dataclasses import dataclass

from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind


@dataclass(frozen=True)
class MergeRecomputedModelChangesTestCase:
    """One resolved-kind x recomputed-kind cell of the change merge matrix."""

    description: str
    resolved_change_kind: ChangeKind
    recomputed_change_kind: ChangeKind | None
    expected_change_kind: ChangeKind
    expected_backfill_action: BackfillAction
    expected_version_hash: str | None
