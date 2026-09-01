"""Public future cursor safety entry point."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.planner._helpers.resolve.future_cursor_safety import (
    resolve_future_cursor_safety,
)
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    CursorInputEvidence,
)
from sqlbuild.spec.contracts.models import FutureCursorsConfig


def apply_future_cursor_safety(
    *,
    bounds: CursorBounds,
    cursor_type: str | None,
    cursor_grain: str | None,
    config: FutureCursorsConfig | None,
    invocation_time: datetime | None,
    has_complete_override: bool,
    input_evidence: tuple[CursorInputEvidence, ...] = (),
) -> CursorBounds:
    """Apply configured future safety to effective cursor bounds."""

    return resolve_future_cursor_safety(
        bounds=bounds,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        config=config,
        invocation_time=invocation_time,
        has_complete_override=has_complete_override,
        input_evidence=input_evidence,
    )
