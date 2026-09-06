"""SQLBuild CLI subprocess factory for Dagster."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlbuild.cli.output.constants import INTEGRATION_RESULT_PATH_ENV
from sqlbuild.integrations.dagster._helpers.invocation import (
    _caller_json_output_path,
    _with_event_output_args,
    _with_json_output_args,
    _with_selected_asset_args,
)
from sqlbuild.integrations.dagster._helpers.invocation_context import (
    dagster_invocation_context,
)
from sqlbuild.integrations.dagster.classes.sqlbuild_cli_invocation import SqlBuildCliInvocation
from sqlbuild.runtime.output_capture.constants import INVOCATION_CONTEXT_ENV


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
    execution_json_owned: bool = execution_json_path is not None
    if execution_json_path is None:
        execution_json_path = _caller_json_output_path(args=resolved_args)
    event_args: tuple[str, ...]
    event_args, event_jsonl_path = _with_event_output_args(
        args=resolved_args,
        context=context,
        dag=dag,
    )
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
