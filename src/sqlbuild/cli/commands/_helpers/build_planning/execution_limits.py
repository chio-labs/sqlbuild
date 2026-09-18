"""Target-scoped build execution-limit enforcement."""

from __future__ import annotations

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.planner.types import PlanAction
from sqlbuild.spec.contracts.models import ExecutionLimitsConfig


def executable_model_count(*, plan: PlanOutput) -> int:
    """Return the number of model entries that would execute."""

    return sum(entry.action != PlanAction.SKIP for entry in plan.model_entries)


def enforce_model_execution_limit(
    *,
    model_count: int,
    target_name: str | None,
    limits: ExecutionLimitsConfig,
) -> None:
    """Reject a build whose expanded model count exceeds its target policy."""

    maximum: int | None = limits.max_models
    if maximum is None or model_count <= maximum:
        return
    target_label: str = target_name or "default"
    raise CliUserError(
        "Build plan exceeds the configured model limit\n\n"
        f"Target:          {target_label}\n"
        f"Selected models: {model_count}\n"
        f"Maximum models:  {maximum}\n"
        "Configuration:   "
        f"targets.{target_label}.execution_limits.max_models\n\n"
        "No warehouse changes were made.",
        code="C413",
        help=limits.remediation,
    )
