"""CLI scenario command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.scenario_execution.runner import (
    run_scenario as run_scenario_command,
)
from sqlbuild.cli.commands.models import ScenarioTestCommandRequest


def run_scenario(request: ScenarioTestCommandRequest) -> int:
    """Run the scenario command."""

    return run_scenario_command(request=request)
