"""Public clone execution JSON formatting entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    format_clone_execution_json as _format_clone_execution_json,
)
from sqlbuild.executor.clone.models import CloneExecutionResult


def format_clone_execution_json(
    *, result: CloneExecutionResult, resource_types_by_name: Mapping[str, str]
) -> str:
    """Format clone command execution results as JSON."""

    return _format_clone_execution_json(
        result=result,
        resource_types_by_name=resource_types_by_name,
    )
