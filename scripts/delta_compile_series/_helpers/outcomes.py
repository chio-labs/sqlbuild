"""Judge what one compile of a delta compile series did."""

from __future__ import annotations

import re

from scripts.delta_compile_series.constants import (
    COMPILE_REUSE_HIT_LINE,
    DELTA_FALLBACK_PATTERN,
    DELTA_MISMATCH_PATTERN,
    DELTA_VERIFIED_LINE,
    MISMATCH_EXIT_CODE,
    STALE_PROBLEMS,
)
from scripts.delta_compile_series.models import DeltaCompileEdit, DeltaCompileOutcome


def fallback_reason(*, outcome: DeltaCompileOutcome) -> str | None:
    """Why the compile fell back from a delta, when it says."""

    reasons: list[str] = re.findall(DELTA_FALLBACK_PATTERN, outcome.stderr, flags=re.MULTILINE)
    return reasons[0] if reasons else None


def judged(
    *, outcome: DeltaCompileOutcome, edit: DeltaCompileEdit, reverted: bool, others_edited: bool
) -> tuple[bool, str | None]:
    """Whether the compile was a verified delta, and what was unexpected about it, if anything."""

    mismatches: list[str] = re.findall(DELTA_MISMATCH_PATTERN, outcome.stderr, flags=re.MULTILINE)
    if outcome.returncode == MISMATCH_EXIT_CODE or mismatches:
        return False, f"mismatch: {mismatches}"
    if COMPILE_REUSE_HIT_LINE in outcome.stderr:
        return False, None if reverted else "replayed a compile after an edit"
    reason: str | None = fallback_reason(outcome=outcome)
    if others_edited and reason is not None and STALE_PROBLEMS in reason:
        return False, None
    if edit.fallback_reason is None:
        verified: bool = DELTA_VERIFIED_LINE in outcome.stderr
        return verified, None if verified else f"fell back: {reason}"
    if reason is None or edit.fallback_reason not in reason:
        return False, f"expected a fallback for {edit.fallback_reason!r}, got {reason!r}"
    return False, None
