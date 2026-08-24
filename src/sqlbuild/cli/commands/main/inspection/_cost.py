"""CLI run-cost history and drill-down entry point."""

from sqlbuild.cli.commands._helpers.cost.command import run_cost_command
from sqlbuild.cli.commands._helpers.cost.refresh import refresh_pending_cost_run
from sqlbuild.cli.commands.models import CostCommandRequest


def run_cost(request: CostCommandRequest) -> int:
    """Render persisted cost history or one run breakdown."""

    _ = refresh_pending_cost_run(request)
    return run_cost_command(request)
