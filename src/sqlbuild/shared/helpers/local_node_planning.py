"""Neutral local node action classification for planner adapters."""

from __future__ import annotations

from sqlbuild.shared.models import LocalNodePlanInput, LocalNodePlanOutcome
from sqlbuild.shared.types import LocalNodePlanAction, LocalNodePlanReason


def classify_local_node_plan(input: LocalNodePlanInput) -> LocalNodePlanOutcome:
    """Classify local node state using planner semantics shared by adapters."""

    if input.full_refresh:
        return LocalNodePlanOutcome(
            action=LocalNodePlanAction.RUN,
            reason=LocalNodePlanReason.FULL_REFRESH,
        )
    if not input.fingerprint_exists:
        return LocalNodePlanOutcome(
            action=LocalNodePlanAction.RUN,
            reason=LocalNodePlanReason.FIRST_RUN,
        )
    if not input.relation_exists:
        return LocalNodePlanOutcome(
            action=LocalNodePlanAction.RUN,
            reason=LocalNodePlanReason.RELATION_MISSING,
        )
    if input.local_hash is not None and input.previous_hash != input.local_hash:
        return LocalNodePlanOutcome(
            action=LocalNodePlanAction.RUN,
            reason=LocalNodePlanReason.LOCAL_CHANGED,
        )
    return LocalNodePlanOutcome(
        action=LocalNodePlanAction.CURRENT,
        reason=LocalNodePlanReason.NO_CHANGE,
    )
