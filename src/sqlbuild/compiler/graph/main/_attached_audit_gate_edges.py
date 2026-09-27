"""Attached-audit ordering edge entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.graph._helpers.audit_gates import attached_audit_gate_edges_impl
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge


def attached_audit_gate_edges(*, project: CompiledProject) -> tuple[AttachedAuditGateEdge, ...]:
    """Return edges from resources an attached audit reads to the nodes the audit gates."""

    return attached_audit_gate_edges_impl(project=project)
