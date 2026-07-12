"""Public load execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output.helpers.execution_protocol_v1 import (
    format_load_execution_json as _format_load_execution_json,
)
from sqlbuild.executor.load.models import LoadExecutionResult


def format_load_execution_json(*, results: tuple[LoadExecutionResult, ...]) -> str:
    """Format load command execution results as JSON."""

    return _format_load_execution_json(results=results)
