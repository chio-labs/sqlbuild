"""Ordering edges that let attached audits gate their target."""

from __future__ import annotations

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


def attached_audit_gate_edges_impl(
    *, project: CompiledProject
) -> tuple[AttachedAuditGateEdge, ...]:
    """Return edges from each extra audit read to its model or seed target, or source dependants."""

    source_dependants: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    for model in project.models:
        for dep in model.deps:
            if dep.resource_type == CompiledResourceType.SOURCE:
                source_dependants.setdefault(dep, []).append(model.key)
    edges: list[AttachedAuditGateEdge] = []
    audit: CompiledAudit
    for audit in project.audits:
        if audit.attached_target_kind is None or audit.attached_target_name is None:
            continue
        target_kind: AttachedAuditTargetKind = AttachedAuditTargetKind(audit.attached_target_kind)
        target: CompiledObjectKey = CompiledObjectKey(
            resource_type=target_kind.resource_type, name=audit.attached_target_name
        )
        gated_keys: tuple[CompiledObjectKey, ...] = (
            tuple(source_dependants.get(target, ()))
            if target_kind is AttachedAuditTargetKind.SOURCE
            else (target,)
        )
        read: CompiledObjectKey
        for read in _extra_reads(audit=audit, target=target):
            edges.extend(
                AttachedAuditGateEdge(audit_name=audit.name, target=target, gated=gated, read=read)
                for gated in gated_keys
            )
    return tuple(dict.fromkeys(edges))


def _extra_reads(
    *, audit: CompiledAudit, target: CompiledObjectKey
) -> tuple[CompiledObjectKey, ...]:
    return tuple(
        read
        for read in audit.scope_deps
        if read != target and read.resource_type in _READABLE_RESOURCE_TYPES
    )


def attached_audit_gate_cycle_impl(*, project: CompiledProject) -> AttachedAuditGateEdge | None:
    """Return the first attached-audit read that depends on the audit's own target."""

    edges: tuple[AttachedAuditGateEdge, ...] = attached_audit_gate_edges_impl(project=project)
    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {
        key: list(deps) for key, deps in build_lineage_upstream_deps_impl(project).items()
    }
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
                return AttachedAuditGateEdge(
                    audit_name=audit.name, target=target, gated=target, read=read
                )
    return None
