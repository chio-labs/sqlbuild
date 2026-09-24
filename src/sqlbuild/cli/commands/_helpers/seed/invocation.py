"""Seed command invocation resolution phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.runtime.command_invocation import (
    resolve_command_invocation,
)
from sqlbuild.cli.commands.models import SeedCommandRequest, SeedInvocation


def resolve_seed_invocation(*, request: SeedCommandRequest) -> SeedInvocation:
    """Resolve discovery, adapter, connection, and output context for seed."""

    return resolve_command_invocation(request=request, invocation_type=SeedInvocation)
