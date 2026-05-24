"""Subprocess runner helpers for ingestr."""

from __future__ import annotations

import shutil
import subprocess
import sys
from os import environ
from pathlib import Path
from typing import TextIO

from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.integrations.ingestr.helpers.output import (
    format_ingestr_command,
    write_external_output,
)
from sqlbuild.shared.helpers.colors import dim, orange_bold


def run_ingestr_command(
    command: tuple[str, ...],
    *,
    stdout_stream: TextIO | None = None,
    stderr_stream: TextIO | None = None,
    use_color: bool = False,
) -> None:
    """Run ingestr and raise a clear integration error when execution fails."""

    if shutil.which(command[0]) is None:
        raise IngestrIntegrationError(
            "This source uses ingestr, but the ingestr CLI is not available. "
            "Install it with: pip install 'sqlbuild[ingestr]'"
        )
    output_stream: TextIO = stdout_stream or sys.stdout
    error_stream: TextIO = stderr_stream or sys.stderr
    execution_label: str = orange_bold("ingestr execution") if use_color else "ingestr execution"
    execution_detail: str = dim("ingestr ingest") if use_color else "ingestr ingest"
    output_stream.write(f"{execution_label}  {execution_detail}\n\n")
    output_stream.write(f"Running ingestr: {format_ingestr_command(command)}\n\n")
    output_stream.flush()
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
    if completed.stdout:
        write_external_output(
            stream=output_stream,
            label="ingestr stdout",
            output=completed.stdout,
        )
    if completed.stderr:
        write_external_output(
            stream=error_stream,
            label="ingestr stderr",
            output=completed.stderr,
        )
    if completed.returncode != 0:
        raise IngestrIntegrationError(f"ingestr failed with exit code {completed.returncode}")


def _ingestr_subprocess_env() -> dict[str, str]:
    env: dict[str, str] = dict(environ)
    if env.get("ADBC_DRIVER_PATH"):
        return env
    driver_path: Path = Path(sys.prefix) / "etc" / "adbc" / "drivers"
    if driver_path.exists():
        env["ADBC_DRIVER_PATH"] = str(driver_path)
    return env
