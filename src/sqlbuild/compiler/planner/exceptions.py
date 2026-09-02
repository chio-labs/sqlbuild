"""Expected planner-stage exception types."""

from __future__ import annotations

from typing import Any


class PlannerInputError(ValueError):
    """Raised when planner inputs cannot be resolved safely."""

    code: str = "S000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class FutureCursorSafetyError(PlannerInputError):
    """Raised when an effective cursor exceeds the configured future limit."""


class MaximumAutomaticStartError(PlannerInputError):
    """Raised when automatic cursor recovery would exceed its configured horizon."""

    def __init__(
        self,
        message: str | None = None,
        *,
        evidence: Any | None = None,
        non_idempotent: bool = False,
    ) -> None:
        self.evidence = evidence
        if message is None and evidence is not None:
            detail: str = " on a non-idempotent materialization" if non_idempotent else ""
            message = (
                "maximum automatic start policy exceeded"
                f"{detail}: physical target MAX='{evidence.physical_target_max}', "
                f"highest eligible MAX={evidence.highest_eligible_target_max!r}, "
                f"effective post-lookback start='{evidence.effective_start}', "
                f"horizon='{evidence.maximum_allowed_start}', action={evidence.action.value}, "
                f"input={evidence.target_relation}.{evidence.cursor_column}"
            )
        super().__init__(message or "maximum automatic start policy exceeded")
