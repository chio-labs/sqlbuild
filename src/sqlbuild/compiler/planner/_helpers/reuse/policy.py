"""Canonical compiler planner reuse policy."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import ReusePolicyNodeFacts
from sqlbuild.compiler.planner.types import StandardReuseDecisionKind


def decide_reuse_for_node(facts: ReusePolicyNodeFacts) -> str:
    """Return the canonical planner reuse decision for one physical node."""

    if (
        facts.expected_identity_present
        and facts.destination_identity_current
        and facts.destination_relation_exists
    ):
        if facts.destination_current_can_reuse_origin:
            return StandardReuseDecisionKind.REUSE_ELIGIBLE.value
        return StandardReuseDecisionKind.CURRENT.value
    if not facts.reuse_eligible_materialization:
        return StandardReuseDecisionKind.INELIGIBLE_MATERIALIZATION.value
    if not facts.reuse_origin_identity_present:
        return StandardReuseDecisionKind.REUSE_ORIGIN_FINGERPRINT_MISSING.value
    if not facts.reuse_origin_relation_exists:
        return StandardReuseDecisionKind.REUSE_ORIGIN_RELATION_MISSING.value
    if not facts.reuse_origin_matches_expected:
        return StandardReuseDecisionKind.REUSE_ORIGIN_VERSION_MISMATCH.value
    if facts.source_freshness_stale:
        return StandardReuseDecisionKind.REUSE_FROM_SOURCE_FRESHNESS_STALE.value
    return StandardReuseDecisionKind.REUSE_ELIGIBLE.value
