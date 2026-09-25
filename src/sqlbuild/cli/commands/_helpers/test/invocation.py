"""Test command invocation resolution phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.runtime.command_invocation import (
    resolve_reported_command_invocation,
)
from sqlbuild.cli.commands.models import TestCommandRequest, TestInvocation


def resolve_test_invocation(*, request: TestCommandRequest) -> TestInvocation:
    """Resolve discovery, adapter, connection, and reporters for test."""

    return resolve_reported_command_invocation(request=request, invocation_type=TestInvocation)
