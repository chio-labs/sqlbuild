"""Ordering edges that let attached audits gate their target."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledAudit, CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, CompiledResourceType
from sqlbuild.compiler.graph._helpers.algorithms import transitive_closure_many_impl
from sqlbuild.compiler.graph._helpers.lineage import build_lineage_upstream_deps_impl
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge

_READABLE_RESOURCE_TYPES: frozenset[CompiledResourceType] = frozenset(
    {
        CompiledResourceType.MODEL,
        CompiledResourceType.SEED,
        CompiledResourceType.SOURCE,
        CompiledResourceType.UDF,
        CompiledResourceType.TABLE_FN,
    }
)


@dataclass(frozen=True)
class _AuditGate:
    audit_name: str
    target_kind: AttachedAuditTargetKind
    target: CompiledObjectKey
    reads: tuple[CompiledObjectKey, ...]


def attached_audit_gate_edges_impl(
    *, project: CompiledProject
) -> tuple[AttachedAuditGateEdge, ...]:
    """Return edges from each extra audit read to its model or seed target, or source triggers."""

    source_triggers: dict[CompiledObjectKey, set[CompiledObjectKey]] = {}
    for model in project.models:
        for dep in model.deps:
            if dep.resource_type == CompiledResourceType.SOURCE:
                source_triggers.setdefault(dep, set()).add(model.key)
    gates: tuple[_AuditGate, ...] = _audit_gates(project=project)
    edges: dict[AttachedAuditGateEdge, None] = {}
    changed: bool = True
    while changed:
        changed = False
        gate: _AuditGate
        for gate in gates:
            edge: AttachedAuditGateEdge
            for edge in _gate_edges(gate=gate, source_triggers=source_triggers):
                if edge in edges:
                    continue
                edges[edge] = None
                changed = True
                if (
                    edge.read.resource_type == CompiledResourceType.SOURCE
                    and edge.gated.resource_type == CompiledResourceType.MODEL
                ):
                    source_triggers.setdefault(edge.read, set()).add(edge.gated)
    return tuple(edges)


def _audit_gates(*, project: CompiledProject) -> tuple[_AuditGate, ...]:
    gates: list[_AuditGate] = []
    audit: CompiledAudit
    for audit in project.audits:
        if audit.attached_target_kind is None or audit.attached_target_name is None:
            continue
        target_kind: AttachedAuditTargetKind = AttachedAuditTargetKind(audit.attached_target_kind)
        target: CompiledObjectKey = CompiledObjectKey(
            resource_type=target_kind.resource_type, name=audit.attached_target_name
        )
        reads: tuple[CompiledObjectKey, ...] = _extra_reads(audit=audit, target=target)
        if reads:
            gates.append(
                _AuditGate(
                    audit_name=audit.name, target_kind=target_kind, target=target, reads=reads
                )
            )
    return tuple(gates)


def _gate_edges(
    *,
    gate: _AuditGate,
    source_triggers: dict[CompiledObjectKey, set[CompiledObjectKey]],
) -> tuple[AttachedAuditGateEdge, ...]:
    gated_keys: tuple[CompiledObjectKey, ...] = (
        tuple(sorted(source_triggers.get(gate.target, ()), key=lambda key: key.name))
        if gate.target_kind is AttachedAuditTargetKind.SOURCE
        else (gate.target,)
    )
    edges: list[AttachedAuditGateEdge] = []
    read: CompiledObjectKey
    for read in gate.reads:
        edges.extend(
            AttachedAuditGateEdge(
                audit_name=gate.audit_name, target=gate.target, gated=gated, read=read
            )
            for gated in gated_keys
        )
    return tuple(edges)


def _extra_reads(
    *, audit: CompiledAudit, target: CompiledObjectKey
) -> tuple[CompiledObjectKey, ...]:
    return tuple(
        read
        for read in audit.scope_deps
        if read != target and read.resource_type in _READABLE_RESOURCE_TYPES
    )


def attached_audit_gate_cycles_impl(
    *, project: CompiledProject
) -> tuple[AttachedAuditGateEdge, ...]:
    """Return every attached-audit read that depends on the audit's own target."""

    edges: tuple[AttachedAuditGateEdge, ...] = attached_audit_gate_edges_impl(project=project)
    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {
        key: list(deps) for key, deps in build_lineage_upstream_deps_impl(project).items()
    }
    cycles: dict[AttachedAuditGateEdge, None] = {}
    edge: AttachedAuditGateEdge
    for edge in edges:
        upstream.setdefault(edge.gated, []).append(edge.read)
    audit: CompiledAudit
    for audit in sorted(project.audits, key=lambda item: item.name):
        if audit.attached_target_kind is None or audit.attached_target_name is None:
            continue
        target: CompiledObjectKey = CompiledObjectKey(
            resource_type=AttachedAuditTargetKind(audit.attached_target_kind).resource_type,
            name=audit.attached_target_name,
        )
        read: CompiledObjectKey
        for read in _extra_reads(audit=audit, target=target):
            if target in transitive_closure_many_impl(
                starts=(read,), edges=upstream, include_starts=False
            ):
                cycles[
                    AttachedAuditGateEdge(
                        audit_name=audit.name, target=target, gated=target, read=read
                    )
                ] = None
    return tuple(
        sorted(cycles, key=lambda item: (item.audit_name, item.target.name, item.read.name))
    )
