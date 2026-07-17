"""CLI dbt scenario command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.scenario_execution.dbt_run import (
    run_dbt_scenario_capture,
    run_dbt_scenario_test,
)
from sqlbuild.cli.commands.constants import (
    DBT_SCENARIO_CAPTURE_SUBCOMMAND,
    DBT_SCENARIO_TEST_SUBCOMMAND,
)


def run_dbt_scenario_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Dispatch `sqb dbt scenario test` or `sqb dbt scenario capture`."""

    if args and args[0] == DBT_SCENARIO_CAPTURE_SUBCOMMAND:
        return run_dbt_scenario_capture(project_dir=project_dir, args=args[1:], no_color=no_color)
    test_args: tuple[str, ...] = (
        args[1:] if args and args[0] == DBT_SCENARIO_TEST_SUBCOMMAND else args
    )
    return run_dbt_scenario_test(project_dir=project_dir, args=test_args, no_color=no_color)
