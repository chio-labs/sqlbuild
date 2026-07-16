"""Test helpers for planner identity merge tests."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    PlannerResolvedActions,
    ResolvedModelAction,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind

MERGE_MODEL_NAME: str = "orders"
MERGE_RESOLVED_HASH: str = "resolved-hash"
MERGE_RECOMPUTED_HASH: str = "recomputed-hash"


def build_resolved_actions(resolved_change_kind: ChangeKind) -> PlannerResolvedActions:
    """Build resolved planner actions for one model with a bounded backfill change."""

    resolved_change: ChangeDetectionResult = ChangeDetectionResult(
        model_name=MERGE_MODEL_NAME,
        change_kind=resolved_change_kind,
        fingerprint_version_hash=MERGE_RESOLVED_HASH,
        backfill=BackfillResult(action=BackfillAction.BOUNDED, duration="7d"),
    )
    return PlannerResolvedActions(
        models={
            MERGE_MODEL_NAME: ResolvedModelAction(
                change=resolved_change,
                backfill=BackfillResult(action=BackfillAction.FULL),
            )
        }
    )


def build_recomputed_models(recomputed_change_kind: ChangeKind) -> dict[str, ChangeDetectionResult]:
    """Build a single-model recomputed change map for the merge tests."""

    return {
        MERGE_MODEL_NAME: ChangeDetectionResult(
            model_name=MERGE_MODEL_NAME,
            change_kind=recomputed_change_kind,
            fingerprint_version_hash=MERGE_RECOMPUTED_HASH,
            backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        )
    }
