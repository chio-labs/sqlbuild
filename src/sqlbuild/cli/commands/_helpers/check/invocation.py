"""Check command invocation resolution phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.runtime.command_invocation import (
    resolve_reported_command_invocation,
)
from sqlbuild.cli.commands.models import CheckCommandRequest, CheckInvocation


def resolve_check_invocation(*, request: CheckCommandRequest) -> CheckInvocation:
    """Resolve discovery, adapter, connection, and reporters for check."""

    return resolve_reported_command_invocation(request=request, invocation_type=CheckInvocation)
