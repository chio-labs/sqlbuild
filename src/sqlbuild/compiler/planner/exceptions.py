"""Expected planner-stage exception types."""

from __future__ import annotations

from typing import Any

from sqlbuild.cursor_algebra.main.render import render


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
                f"{detail}: physical target MAX='{render(value=evidence.physical_target_max)}', "
                "highest eligible MAX="
                f"{self._render_optional_repr(evidence.highest_eligible_target_max)}, "
                "effective post-lookback start="
                f"'{render(value=evidence.effective_start)}', "
                f"horizon='{render(value=evidence.maximum_allowed_start)}', "
                f"action={evidence.action.value}, "
                f"input={evidence.target_relation}.{evidence.cursor_column}"
            )
        super().__init__(message or "maximum automatic start policy exceeded")

    @staticmethod
    def _render_optional_repr(value: Any | None) -> str:
        return "None" if value is None else repr(render(value=value))
