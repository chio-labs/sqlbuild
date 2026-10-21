"""Subprocess runner helpers for ingestr."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from importlib import metadata
from os import environ
from pathlib import Path

from sqlbuild._native import format_ingestr_command
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.integrations.ingestr.models import IngestrCommandResult
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle

_DUCKDB_DRIVER_BOOTSTRAP_ERROR: str = "ADBC driver still not available after installation"
_DUCKDB_MANIFEST: str = "duckdb.toml"


def run_ingestr_command(
    command: tuple[str, ...],
) -> IngestrCommandResult:
    """Run ingestr and raise a clear integration error when execution fails."""

    if shutil.which(command[0]) is None:
        raise IngestrIntegrationError(
            "This source uses ingestr, but the ingestr CLI is not available. "
            "Install it with: pip install 'sqlbuild[ingestr]'"
        )
    ensure_duckdb_driver()
    command_display: str = format_ingestr_command(command)
    try:
        completed: subprocess.CompletedProcess[str] = _run_observed_ingestr_subprocess(
            command=command
        )
        if completed.returncode != 0 and _DUCKDB_DRIVER_BOOTSTRAP_ERROR in completed.stdout:
            completed = _run_observed_ingestr_subprocess(command=command)
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


def _run_ingestr_subprocess(*, command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        env=_ingestr_subprocess_env(),
        text=True,
    )


def _run_observed_ingestr_subprocess(
    *, command: tuple[str, ...]
) -> subprocess.CompletedProcess[str]:
    with OperationLifecycle(
        operation_kind="subprocess",
        operation_name="ingestr_command",
        auto_fail_base_exceptions=False,
    ) as lifecycle:
        completed: subprocess.CompletedProcess[str] = _run_ingestr_subprocess(command=command)
        if completed.returncode == 0:
            lifecycle.completed(exit_code=0)
        else:
            lifecycle.failed(
                error_code=f"exit_{completed.returncode}",
                exit_code=completed.returncode,
                signal_number=-completed.returncode if completed.returncode < 0 else None,
            )
        return completed


def _ingestr_subprocess_env() -> dict[str, str]:
    env: dict[str, str] = dict(environ)
    if env.get("ADBC_DRIVER_PATH"):
        return env
    driver_path: Path = _managed_driver_path()
    if driver_path.exists():
        env["ADBC_DRIVER_PATH"] = str(driver_path)
    return env


def _managed_driver_path() -> Path:
    return Path(sys.prefix) / "etc" / "adbc" / "drivers"


def ensure_duckdb_driver() -> None:
    """Install the DuckDB ADBC driver matching the duckdb package unless the user set one."""

    if environ.get("ADBC_DRIVER_PATH"):
        return
    try:
        duckdb_version: str = metadata.version("duckdb")
    except metadata.PackageNotFoundError:
        return
    driver_path: Path = _managed_driver_path()
    if _installed_driver_version(driver_path / _DUCKDB_MANIFEST) == duckdb_version:
        return
    dbc: str | None = _dbc_executable()
    if dbc is None:
        raise IngestrIntegrationError(
            "ingestr needs the dbc driver installer to pin its DuckDB driver to duckdb "
            f"{duckdb_version}. Install it with: pip install 'sqlbuild[ingestr]'"
        )
    driver_path.mkdir(parents=True, exist_ok=True)
    with OperationLifecycle(
        operation_kind="subprocess",
        operation_name="adbc_driver_install",
        auto_fail_base_exceptions=False,
    ) as lifecycle:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            (dbc, "install", "--quiet", f"duckdb={duckdb_version}"),
            capture_output=True,
            check=False,
            env={**environ, "ADBC_DRIVER_PATH": str(driver_path)},
            text=True,
        )
        if completed.returncode == 0:
            lifecycle.completed(exit_code=0)
        else:
            lifecycle.failed(
                error_code=f"exit_{completed.returncode}",
                exit_code=completed.returncode,
                signal_number=-completed.returncode if completed.returncode < 0 else None,
            )
    if completed.returncode != 0:
        raise IngestrIntegrationError(
            f"could not install the DuckDB ADBC driver for duckdb {duckdb_version}: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )


def _installed_driver_version(manifest: Path) -> str | None:
    try:
        with manifest.open("rb") as handle:
            version: object = tomllib.load(handle).get("version")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return version if isinstance(version, str) else None


def _dbc_executable() -> str | None:
    for name in ("dbc", "dbc.exe"):
        beside_python: Path = Path(sys.executable).parent / name
        if beside_python.exists():
            return str(beside_python)
    return shutil.which("dbc")
