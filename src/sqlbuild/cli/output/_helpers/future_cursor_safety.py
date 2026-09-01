"""Structured future-cursor safety output."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import FutureCursorSafetyEvidence


def serialize_future_cursor_safety(
    evidence: FutureCursorSafetyEvidence | None,
) -> dict[str, object] | None:
    """Serialize cap policy, bounds, and physical input evidence."""

    if evidence is None:
        return None
    return {
        "action": evidence.action.value,
        "max_distance": evidence.max_distance,
        "invocation_time": evidence.invocation_time,
        "discovered_bounds": {
            "start": evidence.discovered_start,
            "end": evidence.discovered_end,
        },
        "applied_bounds": {
            "start": evidence.applied_start,
            "end": evidence.applied_end,
        },
        "maximum_allowed_bounds": {
            "start": evidence.maximum_allowed_start,
            "end": evidence.maximum_allowed_end,
        },
        "future_start_detected": evidence.future_start_detected,
        "future_end_detected": evidence.future_end_detected,
        "determining_input": (
            {
                "relation": evidence.determining_relation,
                "cursor_column": evidence.determining_cursor_column,
            }
            if evidence.determining_relation is not None
            else None
        ),
        "inputs": [
            {
                "relation": item.relation,
                "cursor_column": item.cursor_column,
                "minimum": item.minimum,
                "maximum": item.maximum,
            }
            for item in evidence.inputs
        ],
    }
