"""Public maximum automatic-start warning rendering entry point."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import CursorBounds, MaximumStartSafetyEvidence


def maximum_start_cap_warning(bounds: CursorBounds | None) -> str | None:
    """Render a warning that distinguishes start recovery from future-end capping."""

    if bounds is None or bounds.maximum_start_safety is None:
        return None
    evidence: MaximumStartSafetyEvidence = bounds.maximum_start_safety
    return (
        "AUTOMATIC START CAPPED: physical target MAX "
        f"'{evidence.physical_target_max}' exceeded horizon "
        f"'{evidence.maximum_allowed_start}'; highest eligible target MAX="
        f"{evidence.highest_eligible_target_max!r}, effective post-lookback start="
        f"'{evidence.effective_start}', action={evidence.action.value}, "
        f"input={evidence.target_relation}.{evidence.cursor_column}."
    )
