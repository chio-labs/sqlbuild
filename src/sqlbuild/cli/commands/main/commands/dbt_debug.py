"""CLI-owned dbt debug orchestration."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.cli.commands.main.commands.debug import run_debug as run_sqlbuild_debug
from sqlbuild.integrations.dbt.pipeline.main.debug import debug_dbt_from_project
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.supports_color import supports_color


def run_dbt_debug_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Execute `sqb dbt debug`."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = (not no_color) and supports_color()
    dbt_status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stderr,
        use_color=use_color,
    )
    dbt_status.start("Running dbt debug...")
    try:
        dbt_returncode: int = debug_dbt_from_project(
            project_dir=effective_project_dir,
            args=args,
            stdout_stream=sys.stdout,
            stderr_stream=sys.stderr,
        )
    finally:
        dbt_status.close()
    sys.stdout.write("\n")
    status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stderr,
        use_color=use_color,
    )
    status.start("Running SQLBuild diagnostics...")
    try:
        sqlbuild_returncode: int = run_sqlbuild_debug(
            project_dir=project_dir,
            no_color=no_color,
            no_connection="--no-connection" in args,
            json_output=False,
        )
    finally:
        status.close()
    return 0 if dbt_returncode == 0 and sqlbuild_returncode == 0 else 1
