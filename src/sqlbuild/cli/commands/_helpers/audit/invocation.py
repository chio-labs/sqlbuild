"""Audit command invocation resolution phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.runtime.command_invocation import (
    resolve_reported_command_invocation,
)
from sqlbuild.cli.commands.models import AuditCommandRequest, AuditInvocation


def resolve_audit_invocation(*, request: AuditCommandRequest) -> AuditInvocation:
    """Resolve discovery, adapter, connection, and reporters for audit."""

    return resolve_reported_command_invocation(request=request, invocation_type=AuditInvocation)
