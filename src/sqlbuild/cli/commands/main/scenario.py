"""CLI scenario command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.scenario.runner import run_scenario as run_scenario_command


def run_scenario(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    selectors: tuple[str, ...] = (),
    retain: bool = False,
    local: bool = False,
    strict: bool = False,
) -> int:
    """Run the scenario command."""

    return run_scenario_command(
        project_dir=project_dir,
        no_sql_validation=no_sql_validation,
        no_color=no_color,
        selectors=selectors,
        retain=retain,
        local=local,
        strict=strict,
    )
