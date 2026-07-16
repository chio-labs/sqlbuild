"""Subprocess runner helpers for ingestr."""

from __future__ import annotations

import shutil
import subprocess
import sys
from os import environ
from pathlib import Path

from sqlbuild.integrations.ingestr._helpers.output import format_ingestr_command
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.integrations.ingestr.models import IngestrCommandResult


def run_ingestr_command(
    command: tuple[str, ...],
) -> IngestrCommandResult:
    """Run ingestr and raise a clear integration error when execution fails."""

    if shutil.which(command[0]) is None:
        raise IngestrIntegrationError(
            "This source uses ingestr, but the ingestr CLI is not available. "
            "Install it with: pip install 'sqlbuild[ingestr]'"
        )
    command_display: str = format_ingestr_command(command)
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=_ingestr_subprocess_env(),
            text=True,
        )
    except OSError as error:
        raise IngestrIntegrationError(f"failed to execute ingestr: {error}") from error
    result: IngestrCommandResult = IngestrCommandResult(
        command_display=command_display,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if completed.returncode != 0:
        raise IngestrIntegrationError(
            f"ingestr failed with exit code {completed.returncode}", result
        )
    return result


def _ingestr_subprocess_env() -> dict[str, str]:
    env: dict[str, str] = dict(environ)
    if env.get("ADBC_DRIVER_PATH"):
        return env
    driver_path: Path = Path(sys.prefix) / "etc" / "adbc" / "drivers"
    if driver_path.exists():
        env["ADBC_DRIVER_PATH"] = str(driver_path)
    return env
