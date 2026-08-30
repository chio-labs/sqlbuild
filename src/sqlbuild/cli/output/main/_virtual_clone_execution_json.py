"""Public virtual clone execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    format_virtual_clone_execution_json as _format_virtual_clone_execution_json,
)
from sqlbuild.virtual.executor.models import VirtualCloneResult


def format_virtual_clone_execution_json(*, result: VirtualCloneResult) -> str:
    """Format virtual clone command execution results as JSON."""

    return _format_virtual_clone_execution_json(result=result)
