"""Runtime execution-limit exceptions."""

from __future__ import annotations


class ExecutionDurationLimitError(Exception):
    """Raised when a build exceeds its configured maximum duration."""

    code: str = "C414"

    def __init__(
        self,
        *,
        target_name: str | None,
        max_duration: str,
        remediation: str | None,
    ) -> None:
        target_label: str = target_name or "default"
        self.message = (
            "Build exceeded the configured execution duration\n\n"
            f"Target:            {target_label}\n"
            f"Maximum duration:  {max_duration}\n"
            "Configuration:     "
            f"targets.{target_label}.execution_limits.max_duration\n\n"
            "Warehouse changes may have occurred before the deadline.\n"
            "No additional work will be started, and active warehouse statements were cancelled."
        )
        self.help = remediation
        super().__init__(self.message)


class ItemTimeoutError(Exception):
    """Raised inside one test, scenario or model attempt once its own time limit has passed."""

    code: str = "C417"

    def __init__(self, *, kind: str, name: str, limit: str) -> None:
        super().__init__(f"{kind} '{name}' exceeded its {limit} time limit")
