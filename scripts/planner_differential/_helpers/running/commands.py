"""Run sqb in a fresh process with the harness environment."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from scripts.compiler_differential.constants import GENERATOR_ENVIRONMENT
from scripts.planner_differential.constants import (
    COMMAND_TIMEOUT_SECONDS,
    EXCLUDED_ENVIRONMENT_KEYS,
    EXCLUDED_ENVIRONMENT_PREFIX,
    SQB_ENTRY,
)
from scripts.planner_differential.models import CommandResult

_TIMEOUT_EXIT_CODE: int = -1


def harness_environment() -> dict[str, str]:
    """Return this environment without capture or dbt settings, plus generator variables."""

    return {
        **{
            key: value
            for key, value in os.environ.items()
            if key not in EXCLUDED_ENVIRONMENT_KEYS
            and not key.startswith(EXCLUDED_ENVIRONMENT_PREFIX)
        },
        **GENERATOR_ENVIRONMENT,
    }


def run_sqb(
    *, arguments: tuple[str, ...], project_dir: Path, environment: dict[str, str], python: Path
) -> CommandResult:
    """Run one sqb command in `project_dir`; a timeout reports exit code -1."""

    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            [str(python), "-c", SQB_ENTRY, "--no-color", *arguments],
            cwd=project_dir,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(exit_code=_TIMEOUT_EXIT_CODE, stdout="", stderr="timed out")
    return CommandResult(
        exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )
