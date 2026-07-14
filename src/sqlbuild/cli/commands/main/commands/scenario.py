"""CLI scenario command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.scenario.models import ScenarioTestCommandRequest
from sqlbuild.cli.commands._helpers.scenario.runner import run_scenario as run_scenario_command


def run_scenario(request: ScenarioTestCommandRequest) -> int:
    """Run the scenario command."""

    return run_scenario_command(request=request)
