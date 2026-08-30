"""SQLBuild CLI subprocess factory for Dagster."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlbuild.integrations.dagster._helpers.invocation import (
    _with_json_output_args,
    _with_selected_asset_args,
)
from sqlbuild.integrations.dagster.classes.sqlbuild_cli_invocation import SqlBuildCliInvocation


def start_sqlbuild_cli_invocation(
    *,
    sqb_command: Sequence[str],
    args: Sequence[str],
    project_dir: Path,
    raise_on_error: bool,
    context: Any = None,
    dag: Mapping[str, Any] | None = None,
) -> SqlBuildCliInvocation:
    """Start a SQLBuild CLI subprocess and return its invocation wrapper."""

    selection: tuple[str, ...]
    selector_file: Path | None
    resolved_args: tuple[str, ...]
    selected_args: tuple[str, ...]
    selected_args, selection, selector_file = _with_selected_asset_args(
        args=tuple(args),
        context=context,
        dag=dag,
    )
    execution_json_path: Path | None
    resolved_args, execution_json_path = _with_json_output_args(
        args=selected_args,
        context=context,
        dag=dag,
    )
    command: tuple[str, ...] = (*tuple(sqb_command), *resolved_args)
    process_environment: dict[str, str] = dict(os.environ)
    process_environment["PYTHONUNBUFFERED"] = "1"
    process: subprocess.Popen[str] = subprocess.Popen(
        command,
        cwd=project_dir,
        env=process_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return SqlBuildCliInvocation(
        process=process,
        command=command,
        project_dir=project_dir,
        raise_on_error=raise_on_error,
        context=context,
        dag=dag,
        selection=selection,
        selector_file=selector_file,
        execution_json_path=execution_json_path,
    )
