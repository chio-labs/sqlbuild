"""Selection diagnostics output policy."""

from __future__ import annotations

from typing import cast

from sqlbuild.compiler.planner.models import PlanOutput


def direct_selection_diagnostics_enabled(plan: PlanOutput) -> bool | None:
    """Return the explicit direct diagnostics policy, if present."""

    raw_diagnostics: object | None = plan.metadata.get("selection_diagnostics")
    if not isinstance(raw_diagnostics, dict):
        return None
    diagnostics: dict[str, object] = cast(dict[str, object], raw_diagnostics)
    enabled: object | None = diagnostics.get("enabled")
    return enabled if isinstance(enabled, bool) else None
