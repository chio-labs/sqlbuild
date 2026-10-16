"""SQLBuild CLI subprocess factory for Dagster."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from sqlbuild._native import (
    INTEGRATION_RESULT_PATH_ENV,
    INVOCATION_CONTEXT_ENV,
    dagster_cli_arguments,
)
from sqlbuild.integrations.dagster._helpers.invocation import (
    _selected_asset_check_keys,
    _selected_asset_paths,
)
from sqlbuild.integrations.dagster._helpers.invocation_context import (
    dagster_invocation_context,
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

    planned: dict[str, Any] = dagster_cli_arguments(
        args=_cli_arguments(args),
        dag=dag,
        has_context=context is not None,
        read_selection=lambda: (
            _selected_asset_paths(context=context),
            _selected_asset_check_keys(context=context),
        ),
    )
    event_args: tuple[str, ...] = planned["args"]
    selection: tuple[str, ...] = planned["selection"]
    selector_file: Path | None = planned["selector_file"]
    execution_json_path: Path | None = planned["execution_json_path"]
    execution_json_owned: bool = planned["execution_json_owned"]
    event_jsonl_path: Path | None = planned["event_jsonl_path"]
    command: tuple[str, ...] = (*tuple(sqb_command), *event_args)
    process_environment: dict[str, str] = dict(os.environ)
    process_environment["PYTHONUNBUFFERED"] = "1"
    process_environment.pop(INVOCATION_CONTEXT_ENV, None)
    if context is not None:
        process_environment[INVOCATION_CONTEXT_ENV] = json.dumps(
            dagster_invocation_context(context),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    if event_jsonl_path is not None:
        process_environment[INTEGRATION_RESULT_PATH_ENV] = str(event_jsonl_path)
    process: subprocess.Popen[str] = subprocess.Popen(
        command,
        cwd=project_dir,
        env=process_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    invocation: SqlBuildCliInvocation = SqlBuildCliInvocation(
        process=process,
        command=command,
        project_dir=project_dir,
        raise_on_error=raise_on_error,
        context=context,
        dag=dag,
        selection=selection,
        selector_file=selector_file,
        execution_json_path=execution_json_path,
        event_jsonl_path=event_jsonl_path,
    )
    invocation.execution_json_owned = execution_json_owned
    return invocation


def _cli_arguments(args: Sequence[object]) -> list[str]:
    """Arguments as strings: path-like values pass through, others fail as `str` methods would."""

    arguments: list[str] = []
    for argument in args:
        if isinstance(argument, os.PathLike):
            arguments.append(os.fsdecode(cast("os.PathLike[str]", argument)))
        elif isinstance(argument, str):
            arguments.append(argument)
        else:
            raise AttributeError(
                f"{type(argument).__name__!r} object has no attribute 'startswith'"
            )
    return arguments
