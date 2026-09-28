"""Attached-audit gate cycle detection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.graph._helpers.audit_gates import attached_audit_gate_cycles_impl
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge


def attached_audit_gate_cycles(*, project: CompiledProject) -> tuple[AttachedAuditGateEdge, ...]:
    """Return every attached-audit read that depends on the audit's own target."""

    return attached_audit_gate_cycles_impl(project=project)
