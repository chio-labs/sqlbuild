"""Test command invocation resolution phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.runtime.command_invocation import (
    resolve_reported_command_invocation,
)
from sqlbuild.cli.commands.models import TestCommandRequest, TestInvocation


def resolve_test_invocation(*, request: TestCommandRequest) -> TestInvocation:
    """Resolve test context; ``--inspect`` never connects, so it needs no connection."""

    return resolve_reported_command_invocation(
        request=request,
        invocation_type=TestInvocation,
        require_connection=not request.inspect,
    )
