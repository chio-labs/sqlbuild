"""Public test execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    format_test_execution_json as _format_test_execution_json,
)
from sqlbuild.executor.testing.models import SqlTestExecutionResult


def format_test_execution_json(*, results: tuple[SqlTestExecutionResult, ...]) -> str:
    """Format test command execution results as JSON."""

    return _format_test_execution_json(results=results)
