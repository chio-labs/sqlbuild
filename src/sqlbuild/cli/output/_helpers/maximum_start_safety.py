"""Structured maximum automatic-start safety output."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import MaximumStartSafetyEvidence


def serialize_maximum_start_safety(
    evidence: MaximumStartSafetyEvidence | None,
) -> dict[str, object] | None:
    """Serialize automatic-start policy and physical eligibility evidence."""

    if evidence is None:
        return None
    return {
        "action": evidence.action.value,
        "max_ahead": evidence.max_ahead,
        "invocation_time": evidence.invocation_time,
        "physical_target_max": evidence.physical_target_max,
        "highest_eligible_target_max": evidence.highest_eligible_target_max,
        "effective_start": evidence.effective_start,
        "maximum_allowed_start": evidence.maximum_allowed_start,
        "input": {
            "relation": evidence.target_relation,
            "cursor_column": evidence.cursor_column,
        },
    }
