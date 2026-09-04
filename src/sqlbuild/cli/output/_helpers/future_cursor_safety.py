"""Structured future-cursor safety output."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import FutureCursorSafetyEvidence
from sqlbuild.cursor_algebra.main.render import render


def serialize_future_cursor_safety(
    evidence: FutureCursorSafetyEvidence | None,
) -> dict[str, object] | None:
    """Serialize cap policy, bounds, and physical input evidence."""

    if evidence is None:
        return None
    return {
        "action": evidence.action.value,
        "max_distance": evidence.max_distance,
        "invocation_time": render(value=evidence.invocation_time),
        "discovered_bounds": {
            "start": render(value=evidence.discovered_start),
            "end": render(value=evidence.discovered_end),
        },
        "applied_bounds": {
            "start": render(value=evidence.applied_start),
            "end": render(value=evidence.applied_end),
        },
        "maximum_allowed_bounds": {
            "start": render(value=evidence.maximum_allowed_start),
            "end": render(value=evidence.maximum_allowed_end),
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
                "minimum": render(value=item.minimum) if item.minimum is not None else None,
                "maximum": render(value=item.maximum),
            }
            for item in evidence.inputs
        ],
    }
