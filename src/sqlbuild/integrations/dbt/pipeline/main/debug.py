"""Runtime pipeline for `sqb dbt debug`."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.config import resolve_dbt_config
from sqlbuild.integrations.dbt.helpers.plan_runtime import parse_dbt_config_overrides
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtCommandResult, ResolvedDbtConfig


def debug_dbt_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    dbt_runner: DbtRunner | None = None,
    dbt_executable: str = "dbt",
    stdout_stream: TextIO,
    stderr_stream: TextIO,
) -> int:
    """Run dbt debug from SQLBuild project configuration."""

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    resolved: ResolvedDbtConfig = resolve_dbt_config(
        project_root=project_dir,
        config=discovered_inputs.project_config.dbt,
        overrides=parse_dbt_config_overrides(args),
        require_project_dir=True,
    )
    options: DbtCliOptions = DbtCliOptions(
        project_dir=resolved.project_dir,
        profiles_dir=resolved.profiles_dir,
        target=resolved.target,
    )
    result: DbtCommandResult = (dbt_runner or DbtRunner(dbt_executable=dbt_executable)).debug(
        options=options,
        args=_strip_sqlbuild_and_config_args(args),
    )
    stdout_stream.write(result.stdout)
    stderr_stream.write(result.stderr)
    stdout_stream.flush()
    stderr_stream.flush()
    return result.returncode


def _strip_sqlbuild_and_config_args(args: tuple[str, ...]) -> tuple[str, ...]:
    stripped: list[str] = []
    skip_next: bool = False
    value_flags: set[str] = {"--project-dir", "--profiles-dir", "--target", "--target-path"}
    local_flags: set[str] = {"--no-connection"}
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in local_flags:
            continue
        if arg in value_flags:
            skip_next = index + 1 < len(args)
            continue
        stripped.append(arg)
    return tuple(stripped)
