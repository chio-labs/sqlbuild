"""Public future cursor warning rendering entry point."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import CursorBounds, FutureCursorSafetyEvidence


def future_cursor_cap_warning(bounds: CursorBounds | None) -> str | None:
    """Render a prominent warning for applied future cursor policy."""

    if bounds is None or bounds.future_safety is None:
        return None
    evidence: FutureCursorSafetyEvidence = bounds.future_safety
    return (
        "FUTURE CURSOR CAPPED: discovered bounds "
        f"['{evidence.discovered_start}', '{evidence.discovered_end}'), applied bounds "
        f"['{evidence.applied_start}', '{evidence.applied_end}')."
    )
