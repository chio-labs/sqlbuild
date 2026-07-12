"""Public scenario execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output.helpers.execution_protocol_v1 import (
    format_scenario_execution_json as _format_scenario_execution_json,
)
from sqlbuild.executor.scenario.models import ScenarioRunResult


def format_scenario_execution_json(
    *, results: tuple[ScenarioRunResult, ...], local: bool = False
) -> str:
    """Format scenario test command execution results as JSON."""

    return _format_scenario_execution_json(results=results, local=local)
